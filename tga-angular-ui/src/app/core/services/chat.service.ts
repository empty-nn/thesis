import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  ChatApiResponse,
  ChatMessage,
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

    try {
      const response = environment.useMockApi
        ? await this.mockResponse(trimmed)
        : await firstValueFrom(
            this.http.post<ChatApiResponse>(
              `${environment.apiBaseUrl}/chat`,
              {
                message: trimmed,
                conversation_id: this.conversationId(),
                conversation_history: this.messages()
                  .slice(0, -1)
                  .slice(-6)
                  .map(({ role, content }) => ({ role, content })),
              },
              { withCredentials: true },
            ),
          );

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
  }

  clearUserData(): void {
    this.clear();
    this.conversations.set([]);
    this.isGenerating.set(false);
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
