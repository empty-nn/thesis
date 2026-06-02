import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

function ChatInput() {
  return (
    <div className="border-t border-app-border bg-app-background p-4">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-3xl border border-app-border bg-chat-assistant p-2 shadow-sm">
        <Textarea
          placeholder="Message My Chatbot..."
          className="min-h-10 flex-1 resize-none border-0 bg-transparent text-app-foreground shadow-none placeholder:text-muted-foreground focus-visible:ring-0"
        />

        <Button type="button" size="sm" className="rounded-full">
          Send
        </Button>
      </div>
    </div>
  );
}

export default ChatInput;