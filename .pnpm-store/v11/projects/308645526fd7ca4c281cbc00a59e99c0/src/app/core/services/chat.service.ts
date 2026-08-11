import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  ChatApiResponse,
  ChatMessage,
  PipelineStage,
  PipelineTraceItem,
  ConversationDetail,
  ConversationSummary,
} from '../models/chat.models';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  readonly messages = signal<ChatMessage[]>([
    {
      id: crypto.randomUUID(),
      role: 'assistant',
      createdAt: new Date(),
      content:
        'Hi! I am your **Vietnam Travel Guide Assistant**.\n\n' +
        'Ask me about destinations, activities, transport, food, or trip planning. ' +
        'You can inspect how retrieval works from **Retrieval Debug** in the sidebar.',
    },
  ]);

  readonly isGenerating = signal(false);
  readonly activePipelineStep = signal(0);
  readonly pipelineTrace = signal<PipelineTraceItem[]>([]);
  readonly pipelineStepKeys: readonly PipelineStage[] = [
    'classification',
    'understanding',
    'planning',
    'retrieval',
    'checking',
    'recovery',
    'rechecking',
    'generating',
  ];
  readonly pipelineSteps = [
    'Checking request scope',
    'Understanding your request',
    'Planning what information to find',
    'Retrieving relevant travel information',
    'Checking information coverage',
    'Finding additional information',
    'Rechecking information coverage',
    'Generating your answer',
  ] as const;
  readonly conversationId = signal<string | null>(null);
  readonly conversations = signal<ConversationSummary[]>([]);

  async sendMessage(content: string): Promise<void> {
    const trimmed = content.trim();

    if (!trimmed || this.isGenerating()) {
      return;
    }

    this.messages.update((messages) => [
      ...messages,
      {
        id: crypto.randomUUID(),
        role: 'user',
        content: trimmed,
        createdAt: new Date(),
      },
    ]);

    this.isGenerating.set(true);
    this.activePipelineStep.set(0);
    this.pipelineTrace.set([]);

    try {
      const response = environment.useMockApi
        ? await this.mockResponse(trimmed)
        : await this.streamResponse(trimmed);

      this.conversationId.set(response.conversation_id ?? null);
      if (response.conversation_id) {
        await this.router.navigate([
          '/chat',
          response.conversation_id,
        ]);
      }
      void this.refreshConversations();

      this.messages.update((messages) => [
        ...messages,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.answer,
          sources: response.sources,
          pipelineTrace: [...this.pipelineTrace()],
          createdAt: new Date(),
        },
      ]);
    } catch (error) {
      console.error(error);

      this.messages.update((messages) => [
        ...messages,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          createdAt: new Date(),
          content:
            'I could not reach the backend. Check `environment.ts`, the FastAPI server, and CORS settings.',
        },
      ]);
    } finally {
      this.isGenerating.set(false);
    }
  }

  clear(): void {
    this.messages.set([]);
    this.conversationId.set(null);
    this.pipelineTrace.set([]);
    this.activePipelineStep.set(0);
  }

  clearUserData(): void {
    this.clear();
    this.conversations.set([]);
    this.isGenerating.set(false);
    this.pipelineTrace.set([]);
    this.activePipelineStep.set(0);
  }

  pipelineSummary(stage: PipelineStage): string | undefined {
    return this.pipelineTrace().find((item) => item.stage === stage)?.summary;
  }

  pipelineHighlights(stage: PipelineStage): string[] {
    return this.pipelineTrace().find((item) => item.stage === stage)?.highlights ?? [];
  }

  pipelineHasStage(stage: PipelineStage): boolean {
    return this.pipelineTrace().some((item) => item.stage === stage);
  }

  pipelineLabel(stage: PipelineStage): string {
    const index = this.pipelineStepKeys.indexOf(stage);
    return index >= 0 ? this.pipelineSteps[index] : stage;
  }

  private recordPipelineStage(event: Record<string, unknown>): void {
    const stage = event['stage'] as PipelineStage;
    const index = this.pipelineStepKeys.indexOf(stage);
    if (index < 0) {
      return;
    }

    const {
      type: _type,
      stage: _stage,
      summary,
      highlights,
      ...details
    } = event;
    const item: PipelineTraceItem = {
      stage,
      summary: String(summary ?? 'Stage completed.'),
      highlights: Array.isArray(highlights)
        ? highlights.map((value) => String(value))
        : [],
      details,
    };
    this.pipelineTrace.update((items) => [
      ...items.filter((existing) => existing.stage !== stage),
      item,
    ].sort(
      (left, right) =>
        this.pipelineStepKeys.indexOf(left.stage) -
        this.pipelineStepKeys.indexOf(right.stage),
    ));
    this.activePipelineStep.set(Math.min(index + 1, this.pipelineStepKeys.length - 1));
  }

  private async streamResponse(query: string): Promise<ChatApiResponse> {
    const response = await fetch(
      `${environment.apiBaseUrl}/chat/stream`,
      {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: query,
          conversation_id: this.conversationId(),
          conversation_history: this.messages()
            .slice(0, -1)
            .slice(-6)
            .map(({ role, content }) => ({ role, content })),
        }),
      },
    );

    if (!response.ok || !response.body) {
      throw new Error(`Chat stream failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let completed: ChatApiResponse | null = null;

    const processLine = (line: string): void => {
      if (!line.trim()) {
        return;
      }
      const event = JSON.parse(line) as Record<string, unknown>;
      if (event['type'] === 'stage') {
        this.recordPipelineStage(event);
      } else if (event['type'] === 'complete') {
        completed = {
          answer: String(event['answer'] ?? ''),
          sources: (event['sources'] ?? []) as ChatApiResponse['sources'],
          conversation_id: event['conversation_id'] as string | undefined,
        };
      } else if (event['type'] === 'error') {
        throw new Error(String(event['message'] ?? 'Chat pipeline failed'));
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      lines.forEach(processLine);
      if (done) {
        if (buffer.trim()) {
          processLine(buffer);
        }
        break;
      }
    }

    if (!completed) {
      throw new Error('Chat stream ended without a final answer');
    }
    return completed;
  }

  async refreshConversations(): Promise<void> {
    try {
      const items = await firstValueFrom(
        this.http.get<ConversationSummary[]>(
          `${environment.apiBaseUrl}/conversations`,
          { withCredentials: true },
        ),
      );
      this.conversations.set(items);
    } catch {
      this.conversations.set([]);
    }
  }

  async openConversation(conversationId: string): Promise<void> {
    const conversation = await firstValueFrom(
      this.http.get<ConversationDetail>(
        `${environment.apiBaseUrl}/conversations/${conversationId}`,
        { withCredentials: true },
      ),
    );
    this.conversationId.set(conversation.id);
    this.messages.set(
      conversation.messages.map((message) => ({
        id: String(message.id),
        role: message.role,
        content: message.content,
        createdAt: message.created_at
          ? new Date(message.created_at)
          : new Date(),
      })),
    );
  }

  private async mockResponse(query: string): Promise<ChatApiResponse> {
    await new Promise((resolve) => setTimeout(resolve, 650));

    return {
      answer:
        `### Mock answer\n\n` +
        `You asked: **${query}**\n\n` +
        `This starter is currently using mock mode. When you connect FastAPI, ` +
        `the assistant response will come from your real RAG pipeline.\n\n` +
        `A useful backend flow for this project is:\n\n` +
        `1. Parse query and filters\n` +
        `2. Run **BM25 + vector retrieval**\n` +
        `3. Fuse candidates\n` +
        `4. Apply geographic / metadata boosts\n` +
        `5. Cross-encoder rerank\n` +
        `6. Generate the final cited answer`,
      sources: [
        {
          id: 'mock-1',
          title: 'Mock tourism source',
        },
      ],
    };
  }
}
