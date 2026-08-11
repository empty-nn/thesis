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
}
