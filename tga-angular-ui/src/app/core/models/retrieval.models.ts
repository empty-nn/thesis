export type RetrievalStage =
  | 'vector'
  | 'bm25'
  | 'hybrid'
  | 'rerank'
  | 'final';

export interface RetrievalChunkMetadata {
  country?: string;
  province?: string;
  city?: string;
  placeName?: string;
  placeType?: string;
  chunkTopic?: string;
  travelStyles?: string[];
  activities?: string[];
  suitableFor?: string[];
}

export interface RetrievalChunk {
  id: string;
  rank: number;
  score: number;
  vectorScore?: number;
  bm25Score?: number;
  rerankScore?: number;
  title: string;
  city?: string;
  placeName?: string;
  topic?: string;
  sourceName: string;
  sourceUrl?: string;
  content: string;
  metadata: RetrievalChunkMetadata;
}

export interface RetrievalStageResult {
  stage: RetrievalStage;
  label: string;
  durationMs: number;
  chunks: RetrievalChunk[];
}

export interface RetrievalDebugRun {
  query: string;
  createdAt: Date;
  totalDurationMs: number;
  answer: string;
  stages: Record<RetrievalStage, RetrievalStageResult>;
  diagnostics: RetrievalDebugDiagnostics;
}

export interface RetrievalConfidence {
  level: string;
  score: number;
  evidence_count: number;
  top_score?: number;
  score_gap?: number;
}

export interface RetrievalDebugDiagnostics {
  originalQuery: string;
  rewrittenQuery: string;
  parsedQuery: Record<string, unknown>;
  userMemory: Record<string, unknown>;
  filters: Record<string, unknown>;
  retrievalConfidence?: RetrievalConfidence;
  rewriteDurationMs: number;
  parseDurationMs: number;
  memoryDurationMs: number;
  filterDurationMs: number;
  generationDurationMs: number;
}
