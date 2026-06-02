import ChatHeader from "../components/chat/ChatHeader";
import ChatInput from "../components/chat/ChatInput";
import ChatWindow from "../components/chat/ChatWindow";
import Sidebar from "../components/chat/SideBar";
function ChatPage() {
  return (
    <div className="flex h-screen bg-app-background text-app-foreground">
      <Sidebar />

      <main className="flex flex-1 flex-col">
        <ChatHeader />
        <ChatWindow />
        <ChatInput />
      </main>
    </div>
  );
}

export default ChatPage;