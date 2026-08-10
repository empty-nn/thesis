import { Component, signal } from '@angular/core';

import {
  ChatInputComponent,
  AiResponseComponent,
  TypingIndicatorComponent,
} from '@angular-ai-kit/core';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

@Component({
  selector: 'app-chat',

  imports: [
    ChatInputComponent,
    AiResponseComponent,
    TypingIndicatorComponent,
  ],

  templateUrl: './chat.component.html',
  styleUrl: './chat.component.css',
})
export class ChatComponent {

  messages = signal<ChatMessage[]>([]);
  isLoading = signal(false);

  handleMessage(content: string) {

    if (!content.trim()) {
      return;
    }

    // Add user message
    this.messages.update(messages => [
      ...messages,
      {
        role: 'user',
        content,
        timestamp: new Date(),
      },
    ]);

    this.isLoading.set(true);

    // Simulated API response
    setTimeout(() => {

      this.messages.update(messages => [
        ...messages,
        {
          role: 'assistant',
          content: `
## Sure! I can help you plan your trip.

### Recommended destination

For a first visit to Vietnam, I would recommend **Da Nang and Hoi An**.

- 🏖️ Beautiful beaches
- 🏮 Historic old town
- 🍜 Great local food
- 🚕 Easy transportation
- 💰 Reasonable prices

You could comfortably spend **4–5 days** exploring both destinations.
          `,
          timestamp: new Date(),
        },
      ]);

      this.isLoading.set(false);

    }, 1200);
  }
}