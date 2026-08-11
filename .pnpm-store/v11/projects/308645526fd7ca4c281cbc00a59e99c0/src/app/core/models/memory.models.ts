export interface UserMemoryItem {
  id: number;
  memory_type: string;
  content: string;
  importance: number;
  created_at?: string;
  updated_at?: string;
}
