import type { LucideIcon } from "lucide-react";

export type StepStatus = "idle" | "running" | "completed" | "stopped";

export type StepResultType = "markdown" | "json" | "text";

export type StepOptionType = "text" | "number" | "select" | "checkbox";

export type StepOptionValue = string | number | boolean;
export type DataSourceType = "html-url" | "pdf-upload";

export type StepOption = {
  id: string;
  label: string;
  type: StepOptionType;
  description?: string;
  defaultValue: StepOptionValue;
  options?: {
    label: string;
    value: string;
  }[];
};

export type DataBuildingStep = {
  id: string;
  label: string;
  description: string;
  resultType: StepResultType;
  icon: LucideIcon;
  options?: StepOption[];
};

export type StepResultMap = Record<string, string>;

export type StepStatusMap = Record<string, StepStatus>;

export type StepOptionMap = Record<string, Record<string, StepOptionValue>>;