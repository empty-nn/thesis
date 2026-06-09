import { useRef, useState, type ChangeEvent } from "react";
import {
  Database,
  FileText,
  FileUp,
  Scissors,
  Sparkles,
  Tags,
} from "lucide-react";

import DataBuildingWindow from "../components/data-building/DataBuildingWindow";
import DataSideBar from "../components/data-building/DataSideBar";

import type {
  DataBuildingStep,
  StepOptionMap,
  StepOptionValue,
  StepResultMap,
  StepStatusMap,
  DataSourceType,
} from "../components/data-building/types";
import { cleanMarkdown, convertHtmlUrl, convertPdfUpload, type HtmlConvertMethod, type PdfConvertMethod } from "@/api/dataBuildingApi";

const dataBuildingSteps: DataBuildingStep[] = [
  {
    id: "extract",
    label: "Extract content",
    description: "Convert HTML or PDF into Markdown",
    resultType: "markdown",
    icon: FileUp,
    options: [
      {
        id: "extractMethod",
        label: "Extract methodt",
        type: "select",
        defaultValue: "pymupdf",
        options: [
          { label: "pymupdf", value: "pymupdf" },
          { label: "docling", value: "docling" },
        ],
      },
      {
        id: "outputFormat",
        label: "Output format",
        type: "select",
        defaultValue: "markdown",
        options: [
          { label: "Markdown", value: "markdown" },
          { label: "Plain text", value: "text" },
        ],
      },
      {
        id: "extractMainOnly",
        label: "Extract main content only",
        type: "checkbox",
        defaultValue: true,
        description: "Ignore navbar, footer, sidebar, menu, and ads.",
      },
      {
        id: "keepImages",
        label: "Keep image captions",
        type: "checkbox",
        defaultValue: false,
      },
    ],
  },
  {
    id: "clean",
    label: "Clean Markdown",
    description: "Remove ads, menus, repeated text, and unrelated information",
    resultType: "markdown",
    icon: Scissors,
    options: [
      {
        id: "removeAds",
        label: "Remove ads/newsletter text",
        type: "checkbox",
        defaultValue: true,
      },
      {
        id: "removeRepeatedLines",
        label: "Remove repeated short lines",
        type: "checkbox",
        defaultValue: true,
      },
      {
        id: "minRepeatCount",
        label: "Minimum repeat count",
        type: "number",
        defaultValue: 3,
      },
      {
        id: "keepPictureText",
        label: "Keep picture text",
        type: "checkbox",
        defaultValue: false,
      },
    ],
  },
  {
    id: "metadata",
    label: "Extract metadata",
    description: "Generate tourism metadata as JSON",
    resultType: "json",
    icon: Tags,
    options: [
      {
        id: "model",
        label: "Metadata model",
        type: "select",
        defaultValue: "openai",
        options: [
          { label: "OpenAI", value: "openai" },
          { label: "Local Ollama", value: "ollama" },
        ],
      },
      {
        id: "confidenceThreshold",
        label: "Confidence threshold",
        type: "number",
        defaultValue: 0.7,
      },
      {
        id: "strictJson",
        label: "Strict JSON output",
        type: "checkbox",
        defaultValue: true,
      },
    ],
  },
  {
    id: "chunk",
    label: "Create chunks",
    description: "Split cleaned content into RAG chunks",
    resultType: "json",
    icon: FileText,
    options: [
      {
        id: "chunkSize",
        label: "Chunk size",
        type: "number",
        defaultValue: 1200,
      },
      {
        id: "overlap",
        label: "Chunk overlap",
        type: "number",
        defaultValue: 150,
      },
      {
        id: "splitByHeading",
        label: "Split by Markdown headings",
        type: "checkbox",
        defaultValue: true,
      },
    ],
  },
  {
    id: "store",
    label: "Store in database",
    description: "Save documents and chunks into PostgreSQL",
    resultType: "text",
    icon: Database,
    options: [
      {
        id: "overwriteExisting",
        label: "Overwrite existing document",
        type: "checkbox",
        defaultValue: false,
      },
      {
        id: "markAsVerified",
        label: "Mark as verified",
        type: "checkbox",
        defaultValue: false,
      },
    ],
  },
  {
    id: "embedding",
    label: "Create embeddings",
    description: "Generate vector embeddings for retrieval",
    resultType: "text",
    icon: Sparkles,
    options: [
      {
        id: "embeddingModel",
        label: "Embedding model",
        type: "select",
        defaultValue: "all-MiniLM-L6-v2",
        options: [
          { label: "all-MiniLM-L6-v2", value: "all-MiniLM-L6-v2" },
          {
            label: "OpenAI text-embedding-3-small",
            value: "text-embedding-3-small",
          },
        ],
      },
      {
        id: "batchSize",
        label: "Batch size",
        type: "number",
        defaultValue: 32,
      },
    ],
  },
];

function createInitialStatuses(): StepStatusMap {
  return dataBuildingSteps.reduce<StepStatusMap>((result, step) => {
    result[step.id] = "idle";
    return result;
  }, {});
}

function createInitialOptions(): StepOptionMap {
  return dataBuildingSteps.reduce<StepOptionMap>((result, step) => {
    result[step.id] = {};

    step.options?.forEach((option) => {
      result[step.id][option.id] = option.defaultValue;
    });

    return result;
  }, {});
}

function DataBuilding() {
  const [htmlUrl, setHtmlUrl] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [activeStepId, setActiveStepId] = useState(dataBuildingSteps[0].id);
  const [stepStatuses, setStepStatuses] = useState<StepStatusMap>(createInitialStatuses);
  const [stepResults, setStepResults] = useState<StepResultMap>({});
  const [stepOptions, setStepOptions] = useState<StepOptionMap>(
    createInitialOptions
  );
  const [sourceType, setSourceType] = useState<DataSourceType>("html-url");

  const timerRef = useRef<number | null>(null);
  const runningStepRef = useRef<string | null>(null);

  const hasDataSource = sourceType === "html-url" ? htmlUrl.trim().length > 0 : selectedFile !== null;

  const activeStep =
    dataBuildingSteps.find((step) => step.id === activeStepId) ??
    dataBuildingSteps[0];

  function resetPipelineState() {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = null;
    runningStepRef.current = null;

    setStepStatuses(createInitialStatuses());
    setStepResults({});
    setActiveStepId(dataBuildingSteps[0].id);
  }
  const handleSourceTypeChange = (type: DataSourceType) => {
    setSourceType(type);

    if (type === "html-url") {
      setSelectedFile(null);
    }

    if (type === "pdf-upload") {
      setHtmlUrl("");
    }
  };
  function handleUrlChange(value: string) {
    setHtmlUrl(value);

    if (value.trim().length > 0) {
      setSelectedFile(null);
      setSourceType("html-url");
    }

    resetPipelineState();
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) return;

    setSelectedFile(file);
    setHtmlUrl("");
    setSourceType("pdf-upload");
    resetPipelineState();
  }

  function canRunStep(stepIndex: number) {
    if (!hasDataSource) return false;
    if (runningStepRef.current) return false;

    if (stepIndex === 0) return true;
    const previousStep = dataBuildingSteps[stepIndex - 1];

    return stepStatuses[previousStep.id] === "completed";
  }

  async function handleRunStep(step: DataBuildingStep, stepIndex: number) {
    if (!canRunStep(stepIndex)) return;

    runningStepRef.current = step.id;
    setActiveStepId(step.id);

    setStepStatuses((current) => ({
      ...current,
      [step.id]: "running",
    }));

    setStepResults((current) => ({
      ...current,
      [step.id]: "Processing...",
    }));

    const result = await getFakeStepResult(step.id);

    timerRef.current = window.setTimeout(() => {
      setStepStatuses((current) => ({
        ...current,
        [step.id]: "completed",
      }));

      setStepResults((current) => ({
        ...current,
        [step.id]: result,
      }));

      runningStepRef.current = null;
      timerRef.current = null;
    }, 1000);
  }

  function handleStopStep(stepId: string) {
    if (runningStepRef.current !== stepId) return;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = null;
    runningStepRef.current = null;

    setStepStatuses((current) => ({
      ...current,
      [stepId]: "stopped",
    }));

    setStepResults((current) => ({
      ...current,
      [stepId]: "Stopped by user. You can run this step again.",
    }));
  }

  function handleUpdateStepResult(stepId: string, value: string) {
    setStepResults((current) => ({
      ...current,
      [stepId]: value,
    }));
  }

  function handleUpdateStepOption(stepId: string, optionId: string, value: StepOptionValue) {
    setStepOptions((current) => ({
      ...current,
      [stepId]: {
        ...current[stepId],
        [optionId]: value,
      },
    }));
  }

  async function handleExtract(method: PdfConvertMethod | HtmlConvertMethod) {
    if (sourceType === "pdf-upload") {
      if (!selectedFile) {
        throw new Error("No PDF file selected");
      }

      const result = await convertPdfUpload(
        selectedFile,
        method as PdfConvertMethod
      );

      return result.markdown.markdown;
    }

    if (sourceType === "html-url") {
      if (!htmlUrl.trim()) {
        throw new Error("No HTML URL provided");
      }

      const result = await convertHtmlUrl(
        htmlUrl,
        method as HtmlConvertMethod
      );

      return result.markdown;
    }

    throw new Error("Invalid data source type");
  }

  async function handleCleanMarkdown(md: string) {
    try {
      const result = await cleanMarkdown(md);
      return result;
    } catch (error) {
      console.error(error);
    }
  }

  async function getFakeStepResult(stepId: string) {
    const options = stepOptions[stepId];

    switch (stepId) {
      case "extract":
        const method =
          sourceType === "pdf-upload"
            ? (options["extractMethod"] as PdfConvertMethod)
            : (options["htmlExtractMethod"] as HtmlConvertMethod);

        const markdown = await handleExtract(method);

        return markdown;
      case "clean":
        const md = stepResults['extract']
        const clean_result = await  handleCleanMarkdown(md)
        return clean_result

      case "metadata":
        return ``;

      case "chunk":
        return ``;

      case "store":
        return ``;

      default:
        return "";
    }
  }

  return (
    <div className="flex h-screen bg-app-background text-app-foreground">
      <DataSideBar
        steps={dataBuildingSteps}
        activeStepId={activeStepId}
        stepStatuses={stepStatuses}
        sourceType={sourceType}
        htmlUrl={htmlUrl}
        selectedFile={selectedFile}
        hasDataSource={hasDataSource}
        canRunStep={canRunStep}
        onSelectStep={setActiveStepId}
        onRunStep={handleRunStep}
        onStopStep={handleStopStep}
        onResetPipeline={resetPipelineState}
        onSourceTypeChange={handleSourceTypeChange}
        onUrlChange={handleUrlChange}
        onFileChange={handleFileChange}
      />

      <main className="flex flex-1 flex-col">
        <DataBuildingWindow
          activeStep={activeStep}
          activeStepResult={stepResults[activeStep.id] ?? ""}
          activeStepStatus={stepStatuses[activeStep.id]}
          activeStepOptions={stepOptions[activeStep.id] ?? {}}
          onUpdateResult={(value) =>
            handleUpdateStepResult(activeStep.id, value)
          }
          onUpdateStepOption={(optionId, value) =>
            handleUpdateStepOption(activeStep.id, optionId, value)
          }
        />
      </main>
    </div>
  );
}

export default DataBuilding;