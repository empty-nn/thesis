import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import type {
  DataBuildingStep,
  StepOption,
  StepOptionValue,
  StepStatus,
} from "./types";

type DataBuildingWindowProps = {
  activeStep: DataBuildingStep;
  activeStepResult: string;
  activeStepStatus: StepStatus;
  activeStepOptions: Record<string, StepOptionValue>;
  onUpdateResult: (value: string) => void;
  onUpdateStepOption: (optionId: string, value: StepOptionValue) => void;
};

function DataBuildingWindow({
  activeStep,
  activeStepResult,
  activeStepStatus,
  activeStepOptions,
  onUpdateResult,
  onUpdateStepOption,
}: DataBuildingWindowProps) {
  const [jsonError, setJsonError] = useState("");

  const isJson = activeStep.resultType === "json";

  function handleFormatJson() {
    setJsonError("");

    try {
      const parsed = JSON.parse(activeStepResult);
      const formatted = JSON.stringify(parsed, null, 2);
      onUpdateResult(formatted);
    } catch {
      setJsonError("Invalid JSON. Please fix it before formatting.");
    }
  }

  function renderOption(option: StepOption) {
    const value = activeStepOptions[option.id] ?? option.defaultValue;

    if (option.type === "text") {
      return (
        <Input
          value={String(value)}
          onChange={(event) => onUpdateStepOption(option.id, event.target.value)}
        />
      );
    }

    if (option.type === "number") {
      return (
        <Input
          type="number"
          value={Number(value)}
          onChange={(event) =>
            onUpdateStepOption(option.id, Number(event.target.value))
          }
        />
      );
    }

    if (option.type === "checkbox") {
      return (
        <div className="flex items-center gap-2">
          <Checkbox
            checked={Boolean(value)}
            onCheckedChange={(checked) =>
              onUpdateStepOption(option.id, checked === true)
            }
          />

          <span className="text-sm text-muted-foreground">
            {Boolean(value) ? "Enabled" : "Disabled"}
          </span>
        </div>
      );
    }

    if (option.type === "select") {
      return (
        <Select
          value={String(value)}
          onValueChange={(nextValue) => onUpdateStepOption(option.id, nextValue)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select option" />
          </SelectTrigger>

          <SelectContent>
            {option.options?.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    return null;
  }

  return (
    <div className="flex flex-1 flex-col bg-app-background text-app-foreground">
      <header className="flex h-14 items-center justify-between border-b border-app-border px-5">
        <div>
          <h1 className="text-sm font-medium">{activeStep.label}</h1>
          <p className="text-xs text-muted-foreground">
            {activeStep.description}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-full border border-app-border px-3 py-1 text-xs text-muted-foreground">
            {activeStepStatus}
          </span>

          {isJson && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleFormatJson}
              disabled={!activeStepResult}
            >
              Format JSON
            </Button>
          )}

          <Button size="sm" disabled={!activeStepResult}>
            Save edited result
          </Button>
        </div>
      </header>

      <section className="grid flex-1 grid-cols-1 gap-4 p-5 lg:grid-cols-[1fr_360px]">
        <div className="flex min-h-0 flex-col rounded-xl border border-app-border bg-chat-assistant shadow-sm">
          <div className="border-b border-app-border px-4 py-3">
            <h2 className="text-sm font-medium">Editable result</h2>
            <p className="text-xs text-muted-foreground">
              Remove unrelated information here before running the next step.
            </p>
          </div>

          <Textarea
            value={activeStepResult}
            onChange={(event) => onUpdateResult(event.target.value)}
            placeholder="Run a step from the sidebar. The result will appear here."
            className="min-h-[calc(100vh-210px)] flex-1 resize-none rounded-none border-0 bg-transparent p-4 font-mono text-sm leading-6 text-app-foreground shadow-none focus-visible:ring-0"
          />
        </div>

        <aside className="rounded-xl border border-app-border bg-chat-assistant p-4 shadow-sm">
          <h3 className="text-sm font-medium">Processing options</h3>

          <p className="mt-1 text-xs text-muted-foreground">
            Configure this step before clicking Run step in the sidebar.
          </p>

          <div className="mt-4 space-y-4">
            {activeStep.options && activeStep.options.length > 0 ? (
              activeStep.options.map((option) => (
                <div key={option.id} className="space-y-2">
                  <div>
                    <label className="text-sm font-medium">
                      {option.label}
                    </label>

                    {option.description && (
                      <p className="text-xs text-muted-foreground">
                        {option.description}
                      </p>
                    )}
                  </div>

                  {renderOption(option)}
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">
                This step has no configurable options.
              </p>
            )}
          </div>

          <div className="mt-6 rounded-lg border border-app-border p-3">
            <p className="text-xs font-medium text-app-foreground">
              Current step
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {activeStep.label}
            </p>

            <p className="mt-3 text-xs font-medium text-app-foreground">
              Result type
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {activeStep.resultType}
            </p>
          </div>

          {jsonError && (
            <div className="mt-4 rounded-lg border border-destructive p-3 text-sm text-destructive">
              {jsonError}
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}

export default DataBuildingWindow;