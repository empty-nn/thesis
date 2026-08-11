export type ChatRole = 'user' | 'assistant';

export interface ChatSource {
  id: string;
  title: string;
  url?: string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: Date;
  sources?: ChatSource[];
}

export interface ChatApiResponse {
  answer: string;
  sources?: ChatSource[];
  conversation_id?: string;
}

export interface ConversationSummary {
  id: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ConversationDetail {
  id: string;
  title?: string;
  messages: Array<{
    id: number;
    role: ChatRole;
    content: string;
    created_at?: string;
  }>;
}
