import { FormsModule } from '@angular/forms';
import { Component, inject, signal } from '@angular/core';
import { MarkdownComponent } from 'ngx-markdown';
import {
  LucideBot,
  LucideCopy,
  LucideRefreshCw,
  LucideSend,
  LucideSparkles,
  LucideUser,
} from '@lucide/angular';

import { ChatMessage } from '../../core/models/chat.models';
import { ChatService } from '../../core/services/chat.service';

@Component({
  selector: 'app-chat-page',
  imports: [
    FormsModule,
    MarkdownComponent,
    LucideBot,
    LucideCopy,
    LucideRefreshCw,
    LucideSend,
    LucideSparkles,
    LucideUser,
  ],
  templateUrl: './chat-page.component.html',
})
export class ChatPageComponent {
  protected readonly chat = inject(ChatService);
  protected readonly draft = signal('');

  protected async send(): Promise<void> {
    const message = this.draft();
    this.draft.set('');
    await this.chat.sendMessage(message);
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.send();
    }
  }

  protected copyMessage(message: ChatMessage): void {
    void navigator.clipboard.writeText(message.content);
  }

  protected regenerate(message: ChatMessage): void {
    if (message.role !== 'assistant') {
      return;
    }

    const messages = this.chat.messages();
    const assistantIndex = messages.findIndex(
      (item) => item.id === message.id,
    );

    if (assistantIndex <= 0) {
      return;
    }

    const previousUserMessage = [...messages]
      .slice(0, assistantIndex)
      .reverse()
      .find((item) => item.role === 'user');

    if (previousUserMessage) {
      void this.chat.sendMessage(previousUserMessage.content);
    }
  }
}
