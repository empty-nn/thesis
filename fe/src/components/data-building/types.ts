import { Database, FileText, FileUp, Scissors, Sparkles, Tags, type LucideIcon } from "lucide-react";

export const dataBuildingSteps: DataBuildingStep[] = [
  {
    id: "extract",
    label: "Extract content",
    description: "Convert HTML or PDF into Markdown",
    resultType: "markdown",
    icon: FileUp,
    options: [
      {
        id: "pdfExtractMethod",
        label: "PDF extract method",
        type: "select",
        defaultValue: "pymupdf",
        visibleFor: ["pdf-upload"],
        options: [
          { label: "PyMuPDF", value: "pymupdf" },
          { label: "Docling", value: "docling" },
        ],
      },
      {
        id: "htmlExtractMethod",
        label: "HTML extract method",
        type: "select",
        defaultValue: "trafilatura",
        visibleFor: ["html-url"],
        options: [
          { label: "Trafilatura", value: "trafilatura" },
          { label: "Readability", value: "readability" },
          { label: "jusText", value: "justext" },
          { label: "BoilerPy3", value: "boilerpy3" },
          { label: "Inscriptis", value: "inscriptis" },
          { label: "Markdownify", value: "markdownify" },
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
export type StepStatus = "idle" | "running" | "completed" | "stopped" | "saved";

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
  visibleFor?: DataSourceType[];
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
export type PdfConvertMethod = "pymupdf" | "docling";
export type HtmlConvertMethod =    | "trafilatura"
  | "readability"
  | "justext"
  | "boilerpy3"
  | "inscriptis";