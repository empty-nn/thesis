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
} from "./types";

type DataSideBarProps = {
  steps: DataBuildingStep[];
  activeStepId: string;
  stepStatuses: StepStatusMap;

  htmlUrl: string;
  selectedFile: File | null;
  hasDataSource: boolean;

  canRunStep: (stepIndex: number) => boolean;
  onSelectStep: (stepId: string) => void;
  onRunStep: (step: DataBuildingStep, stepIndex: number) => void;
  onStopStep: (stepId: string) => void;
  onResetPipeline: () => void;
  onUrlChange: (value: string) => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
};

function DataSideBar({
  steps,
  activeStepId,
  stepStatuses,
  htmlUrl,
  selectedFile,
  hasDataSource,
  canRunStep,
  onSelectStep,
  onRunStep,
  onStopStep,
  onResetPipeline,
  onUrlChange,
  onFileChange,
}: DataSideBarProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  function getStatusIcon(status: StepStatus) {
    if (status === "running") {
      return <Loader2 className="h-4 w-4 animate-spin text-sidebar-muted" />;
    }

    if (status === "completed") {
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    }

    if (status === "stopped") {
      return <Square className="h-4 w-4 text-yellow-500" />;
    }

    return <Circle className="h-4 w-4 text-sidebar-muted" />;
  }

  return (
    <aside className="hidden w-80 flex-col border-r border-sidebar-border bg-sidebar p-3 text-sidebar-foreground md:flex">
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
            Add one HTML URL or upload one PDF.
          </p>
        </div>

        <div className="space-y-2">
          <div className="relative">
            <Link className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-sidebar-muted" />

            <Input
              value={htmlUrl}
              onChange={(event) => onUrlChange(event.target.value)}
              placeholder="Paste HTML URL..."
              className="border-sidebar-border bg-transparent pl-9 text-sidebar-foreground placeholder:text-sidebar-muted"
            />
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={onFileChange}
          />

          <Button
            variant="outline"
            className="w-full justify-start gap-2 border-sidebar-border bg-transparent text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-foreground"
            onClick={() => fileInputRef.current?.click()}
          >
            <FileUp className="h-4 w-4" />
            {selectedFile ? selectedFile.name : "Upload PDF"}
          </Button>
        </div>
      </div>

      <Separator className="my-4 bg-sidebar-border" />

      <div className="space-y-3">
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

        <div className="space-y-2">
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
                <button
                  type="button"
                  className="flex w-full items-start gap-3 text-left"
                  onClick={() => onSelectStep(step.id)}
                >
                  <Icon className="mt-0.5 h-4 w-4 text-sidebar-muted" />

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-sidebar-foreground">
                        {step.label}
                      </p>

                      {getStatusIcon(status)}
                    </div>

                    <p className="mt-1 text-xs text-sidebar-muted">
                      {step.description}
                    </p>
                  </div>
                </button>

                <div className="mt-3 flex gap-2">
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
                      Run step
                    </Button>
                  )}
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