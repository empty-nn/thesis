import { Avatar, AvatarFallback } from "@/components/ui/avatar";

type ChatMessageProps = {
  role: "user" | "assistant";
  text: string;
};

function ChatMessage({ role, text }: ChatMessageProps) {
  const isUser = role === "user";

  if (isUser) {
    return (
      <div className="flex items-start justify-end gap-3">
        <div className="max-w-[75%] rounded-2xl bg-chat-user px-4 py-3 text-sm leading-6 text-chat-user-foreground">
          {text}
        </div>

        <Avatar className="h-8 w-8">
          <AvatarFallback className="bg-app-foreground text-xs text-app-background">
            You
          </AvatarFallback>
        </Avatar>
      </div>
    );
  }

  return (
    <div className="flex items-start justify-start gap-3">
      <Avatar className="h-8 w-8">
        <AvatarFallback className="bg-chat-ai text-xs text-white">
          AI
        </AvatarFallback>
      </Avatar>

      <div className="max-w-[75%] rounded-2xl border border-chat-assistant-border bg-chat-assistant px-4 py-3 text-sm leading-6 text-chat-assistant-foreground shadow-sm">
        {text}
      </div>
    </div>
  );
}

export default ChatMessage;