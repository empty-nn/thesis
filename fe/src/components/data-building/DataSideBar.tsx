import { useRef, type ChangeEvent } from "react";
import {
  CheckCircle2,
  Circle,
  FileUp,
  Link,
  Loader2,
  Sidebar as SidebarIcon,
  Square,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

import type {
  DataBuildingStep,
  StepStatus,
  StepStatusMap,
  DataSourceType,
} from "./types";

type DataSideBarProps = {
  steps: DataBuildingStep[];
  activeStepId: string;
  stepStatuses: StepStatusMap;
  
  sourceType: DataSourceType;
  htmlUrl: string;
  selectedFile: File | null;
  hasDataSource: boolean;

  canRunStep: (stepIndex: number) => boolean;
  onSelectStep: (stepId: string) => void;
  onRunStep: (step: DataBuildingStep, stepIndex: number) => void;
  onStopStep: (stepId: string) => void;
  onResetPipeline: () => void;
  onSourceTypeChange: (type: DataSourceType) => void;
  onUrlChange: (value: string) => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
};

function DataSideBar({
  steps,
  activeStepId,
  stepStatuses,
  sourceType,
  htmlUrl,
  selectedFile,
  hasDataSource,
  canRunStep,
  onSelectStep,
  onRunStep,
  onStopStep,
  onResetPipeline,
  onSourceTypeChange,
  onUrlChange,
  onFileChange,
}: DataSideBarProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const handleChangeToHtmlUrl = () => {
  onSourceTypeChange("html-url");

  if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleChangeToPdfUpload = () => {
    onSourceTypeChange("pdf-upload");
  };

  function getStatusIcon(status: StepStatus) {
    if (status === "running") {
      return <Loader2 className="h-4 w-4 animate-spin text-sidebar-muted" />;
    }

    if (status === "completed" || status === "saved") {
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    }

    if (status === "stopped") {
      return <Square className="h-4 w-4 text-yellow-500" />;
    }

    return <Circle className="h-4 w-4 text-sidebar-muted" />;
  }

  return (
    <aside className="hidden h-full min-h-0 w-80 shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar p-3 text-sidebar-foreground md:flex">
      <div className="shrink-0">
        <div className="flex items-center justify-between px-2">
          <div>
            <div className="text-xl font-bold tracking-tight">TGA</div>
            <div className="text-xs text-sidebar-muted">
              Travel Guide Assistant
            </div>
          </div>

          <Button
            variant="ghost"
            size="icon"
            className="text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground"
          >
            <SidebarIcon className="h-5 w-5" />
          </Button>
        </div>

        <Separator className="my-4 bg-sidebar-border" />

        <div className="space-y-3">
          <div>
            <p className="mb-1 px-1 text-xs font-medium text-sidebar-muted">
              Data source
            </p>
            <p className="px-1 text-xs text-sidebar-muted">
              Choose one source: HTML URL or PDF upload.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={sourceType === "html-url" ? "default" : "outline"}
              className="w-full"
              onClick={handleChangeToHtmlUrl}
            >
              HTML URL
            </Button>

            <Button
              type="button"
              variant={sourceType === "pdf-upload" ? "default" : "outline"}
              className="w-full"
              onClick={handleChangeToPdfUpload}
            >
              PDF
            </Button>
          </div>

          {sourceType === "html-url" && (
            <div className="relative">
              <Link className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-sidebar-muted" />

              <Input
                value={htmlUrl}
                onChange={(event) => onUrlChange(event.target.value)}
                placeholder="Paste HTML URL..."
                className="border-sidebar-border bg-transparent pl-9 text-sidebar-foreground placeholder:text-sidebar-muted"
              />
            </div>
          )}

          {sourceType === "pdf-upload" && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={onFileChange}
              />

              <Button
                type="button"
                variant="outline"
                className="w-full justify-start gap-2 border-sidebar-border bg-transparent text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground"
                onClick={() => fileInputRef.current?.click()}
              >
                <FileUp className="h-4 w-4" />
                {selectedFile ? selectedFile.name : "Upload PDF"}
              </Button>
            </>
          )}
        </div>

        <Separator className="my-4 bg-sidebar-border" />
      </div>

      <div className="flex min-h-0 flex-1 flex-col space-y-3">
        <div className="shrink-0">
          <div className="flex items-center justify-between">
            <p className="px-1 text-xs font-medium text-sidebar-muted">
              Data flow
            </p>

            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground"
              onClick={onResetPipeline}
            >
              Reset
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {steps.map((step, index) => {
            const Icon = step.icon;
            const status = stepStatuses[step.id];
            const isRunning = status === "running";
            const isActive = activeStepId === step.id;
            const runDisabled = !hasDataSource || !canRunStep(index);

            return (
              <div
                key={step.id}
                className={`rounded-xl border p-3 ${
                  isActive
                    ? "border-primary bg-sidebar-hover"
                    : "border-sidebar-border"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-start gap-3 text-left"
                    onClick={() => onSelectStep(step.id)}
                  >
                    <Icon className="mt-0.5 h-4 w-4 shrink-0 text-sidebar-muted" />

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-sm font-medium text-sidebar-foreground">
                          {step.label}
                        </p>

                        {getStatusIcon(status)}
                      </div>

                      <p className="mt-1 line-clamp-2 text-xs text-sidebar-muted">
                        {step.description}
                      </p>
                    </div>
                  </button>

                  <div className="shrink-0">
                    {isRunning ? (
                      <Button
                        size="sm"
                        variant="destructive"
                        className="h-8"
                        onClick={() => onStopStep(step.id)}
                      >
                        Stop
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        className="h-8"
                        disabled={runDisabled}
                        onClick={() => onRunStep(step, index)}
                      >
                        Run
                      </Button>
                    )}
                  </div>
                </div>
            </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

export default DataSideBar;