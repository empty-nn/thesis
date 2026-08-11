import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  ChatApiResponse,
  ChatMessage,
} from '../models/chat.models';
import { AuthService } from './auth.service';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

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
                user_id: this.auth.currentUser()?.id,
              },
            ),
          );

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
