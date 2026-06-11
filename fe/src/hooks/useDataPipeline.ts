import { type ChangeEvent, useEffect, useRef, useState } from "react";

import {
  cleanMarkdown,
  convertHtmlUrl,
  convertPdfUpload,
} from "@/api/dataBuildingApi";

import {
  dataBuildingSteps,
  type DataBuildingStep,
  type DataSourceType,
  type HtmlConvertMethod,
  type PdfConvertMethod,
  type StepOptionMap,
  type StepOptionValue,
  type StepResultMap,
  type StepStatusMap,
} from "@/components/data-building/types";

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


export function useDataPipeline() {
  const [htmlUrl, setHtmlUrl] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const [sourceType, setSourceType] =
    useState<DataSourceType>("html-url");

  const [activeStepId, setActiveStepId] = useState(
    dataBuildingSteps[0].id
  );

  const [stepStatuses, setStepStatuses] =
    useState<StepStatusMap>(createInitialStatuses);

  const [stepResults, setStepResults] =
    useState<StepResultMap>({});

  const [stepOptions, setStepOptions] =
    useState<StepOptionMap>(createInitialOptions);

  const timerRef = useRef<number | null>(null);
  const runningStepRef = useRef<string | null>(null);

  const hasDataSource =
    sourceType === "html-url"
      ? htmlUrl.trim().length > 0
      : selectedFile !== null;

  const activeStep =
    dataBuildingSteps.find((step) => step.id === activeStepId) ??
    dataBuildingSteps[0];

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

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

  function handleSourceTypeChange(type: DataSourceType) {
    setSourceType(type);

    if (type === "html-url") {
      setSelectedFile(null);
    }

    if (type === "pdf-upload") {
      setHtmlUrl("");
    }

    resetPipelineState();
  }

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

  async function handleRunStep(
    step: DataBuildingStep,
    stepIndex: number
  ) {
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

    try {
      const result = await getStepResult(step.id);

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
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unknown error occurred.";

      setStepStatuses((current) => ({
        ...current,
        [step.id]: "stopped",
      }));

      setStepResults((current) => ({
        ...current,
        [step.id]: message,
      }));

      runningStepRef.current = null;
      timerRef.current = null;
    }
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

  function handleUpdateStepOption(
    stepId: string,
    optionId: string,
    value: StepOptionValue
  ) {
    setStepOptions((current) => ({
      ...current,
      [stepId]: {
        ...current[stepId],
        [optionId]: value,
      },
    }));
  }

  async function handleExtract(
    method: PdfConvertMethod | HtmlConvertMethod
  ) {
    if (sourceType === "pdf-upload") {
      if (!selectedFile) {
        throw new Error("No PDF file selected");
      }

      const result = await convertPdfUpload(
        selectedFile,
        method as PdfConvertMethod
      );

      // Better backend shape should be result.markdown.
      // Keep this if your current backend returns nested markdown.
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
    const result = await cleanMarkdown(md);
    return result;
  }

  async function getStepResult(stepId: string) {
    const options = stepOptions[stepId];

    switch (stepId) {
      case "extract": {
        const method =
          sourceType === "pdf-upload"
            ? (options["pdfExtractMethod"] as PdfConvertMethod)
            : (options["htmlExtractMethod"] as HtmlConvertMethod);

        const markdown = await handleExtract(method);

        return markdown;
      }

      case "clean": {
        const md = stepResults["extract"];

        if (typeof md !== "string" || !md.trim()) {
          throw new Error("No extracted Markdown found.");
        }

        const cleanResult = await handleCleanMarkdown(md);

        return cleanResult;
      }

      case "metadata":
        return "";

      case "chunk":
        return "";

      case "store":
        return "";

      default:
        return "";
    }
  }

  return {
    state: {
      htmlUrl,
      selectedFile,
      sourceType,
      activeStepId,
      activeStep,
      stepStatuses,
      stepResults,
      stepOptions,
      hasDataSource,
    },

    actions: {
      setActiveStepId,
      resetPipelineState,
      handleSourceTypeChange,
      handleUrlChange,
      handleFileChange,
      canRunStep,
      handleRunStep,
      handleStopStep,
      handleUpdateStepResult,
      handleUpdateStepOption,
    },
  };
}