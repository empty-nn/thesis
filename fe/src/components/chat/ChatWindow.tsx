import { ScrollArea } from "@/components/ui/scroll-area";
import ChatMessage from "./ChatMessage";

function ChatWindow() {
  return (
    <ScrollArea className="flex-1 bg-app-background">
      <section className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8">
        <div className="py-16 text-center">
          <h2 className="text-3xl font-semibold text-app-foreground">
            How can I help you today?
          </h2>

          <p className="mt-3 text-sm text-muted-foreground">
            This is a GPT-style UI test using shadcn/ui.
          </p>
        </div>

        <ChatMessage
          role="user"
          text="I want to build a chatbot UI with React."
        />

        <ChatMessage
          role="assistant"
          text="Sure. This layout uses shadcn Button, Textarea, ScrollArea, Separator, and Avatar components."
        />
      </section>
    </ScrollArea>
  );
}

export default ChatWindow;