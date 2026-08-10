// src/app/components/chat/chat.component.ts
import { Component, inject } from '@angular/core';
import { ChatInputComponent } from '@angular-ai-kit/core';
import { ChatService } from '../../services/chat.service';
import { DatePipe } from '@angular/common';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [ChatInputComponent,
    DatePipe
  ],
  template: `
    <div class="flex flex-col h-screen max-w-3xl mx-auto p-4">
      <!-- Chat Header -->
      <header class="py-3 border-b mb-4 flex items-center justify-between">
        <h1 class="text-xl font-bold">AI Assistant</h1>
        <span class="text-xs text-gray-500">Angular v21.2</span>
      </header>

      <!-- Message History Container -->
      <div class="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
        @for (msg of chatService.messages(); track msg.id) {
          <div 
            class="flex flex-col max-w-[80%]"
            [class.ml-auto]="msg.sender === 'user'"
            [class.items-end]="msg.sender === 'user'"
            [class.items-start]="msg.sender === 'assistant'"
          >
            <div 
              class="rounded-2xl px-4 py-2.5 text-sm"
              [class.bg-blue-600]="msg.sender === 'user'"
              [class.text-white]="msg.sender === 'user'"
              [class.bg-gray-100]="msg.sender === 'assistant'"
              [class.dark:bg-gray-800]="msg.sender === 'assistant'"
            >
              {{ msg.content }}
            </div>
            <span class="text-[10px] text-gray-400 mt-1 px-1">
              {{ msg.timestamp | date:'shortTime' }}
            </span>
          </div>
        }

        @if (chatService.isGenerating()) {
          <div class="text-xs text-gray-400 italic">Thinking...</div>
        }
      </div>

      <!-- Angular AI Kit Input Primitive -->
      <div class="border-t pt-3">
        <ai-chat-input 
          [disabled]="chatService.isGenerating()"
          (send)="handleSend($event)"
          placeholder="Ask anything..."
        />
      </div>
    </div>
  `
})
export class ChatComponent {
  chatService = inject(ChatService);

  handleSend(event: any) {
  // If the component emits a string directly or an event object with detail/value
  const text = typeof event === 'string' ? event : event?.detail?.value || event?.target?.value || '';
  if (text.trim()) {
    this.chatService.sendMessage(text);
  }
}
}