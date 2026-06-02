import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

function Sidebar() {
  return (
    <aside className="hidden w-64 flex-col border-r border-sidebar-border bg-sidebar p-3 text-sidebar-foreground md:flex">
      <Button
        variant="outline"
        className="w-full justify-start border-sidebar-border bg-transparent text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground"
      >
        + New chat
      </Button>

      <Separator className="my-4 bg-sidebar-border" />

      <p className="mb-2 px-2 text-xs text-sidebar-muted">Recent</p>

      <div className="space-y-1">
        <Button
          variant="ghost"
          className="w-full justify-start text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground"
        >
          React chatbot UI
        </Button>

        <Button
          variant="ghost"
          className="w-full justify-start text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground"
        >
          Travel RAG assistant
        </Button>

        <Button
          variant="ghost"
          className="w-full justify-start text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground"
        >
          Thesis idea
        </Button>
      </div>
    </aside>
  );
}

export default Sidebar;