import ThemeSwitcher from "../ThemeSwitcher";

function ChatHeader() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-app-border bg-app-background px-5">
      <h1 className="text-sm font-medium text-app-foreground">My Chatbot</h1>

      <ThemeSwitcher />
    </header>
  );
}

export default ChatHeader;