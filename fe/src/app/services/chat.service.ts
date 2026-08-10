// src/app/services/chat.service.ts
import { Injectable, signal, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface Message {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private http = inject(HttpClient);
  
  // State signals
  messages = signal<Message[]>([
    {
      id: '1',
      sender: 'assistant',
      content: 'Hello! How can I assist you today?',
      timestamp: new Date()
    }
  ]);
  isGenerating = signal<boolean>(false);

  sendMessage(userContent: string) {
    if (!userContent.trim()) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      sender: 'user',
      content: userContent,
      timestamp: new Date()
    };

    // Update state reactively
    this.messages.update((msgs) => [...msgs, userMessage]);
    this.isGenerating.set(true);

    // Call your LLM backend (e.g., FastAPI, Node/Express, or Genkit)
    this.http.post<{ response: string }>('/api/chat', { prompt: userContent }).subscribe({
      next: (res) => {
        const assistantMessage: Message = {
          id: crypto.randomUUID(),
          sender: 'assistant',
          content: res.response,
          timestamp: new Date()
        };
        this.messages.update((msgs) => [...msgs, assistantMessage]);
        this.isGenerating.set(false);
      },
      error: (err) => {
        console.error('Chat error:', err);
        this.isGenerating.set(false);
      }
    });
  }
}