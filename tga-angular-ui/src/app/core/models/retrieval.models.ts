export type RetrievalStage =
  | 'vector'
  | 'bm25'
  | 'hybrid'
  | 'rerank'
  | 'final';

export interface RetrievalChunkMetadata {
  country: string;
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
  id: number;
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
  stages: Record<RetrievalStage, RetrievalStageResult>;
}
