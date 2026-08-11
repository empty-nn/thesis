import { FormsModule } from '@angular/forms';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-chat-page',
  imports: [
    FormsModule,
    MarkdownComponent,
    RouterLink,
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
  protected readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly draft = signal('');

  constructor() {
    void this.chat.refreshConversations();
    this.route.paramMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => {
        const conversationId = params.get('conversationId');
        if (
          conversationId &&
          conversationId !== this.chat.conversationId()
        ) {
          void this.chat.openConversation(conversationId);
        }
      });
  }

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
