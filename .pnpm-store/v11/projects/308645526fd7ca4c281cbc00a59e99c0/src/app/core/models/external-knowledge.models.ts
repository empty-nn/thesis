export interface ExternalKnowledgeSummary {
  totalRecords: number;
  pendingReview: number;
  successfulRecoveries: number;
  uniqueSources: number;
  uncoveredRequirements: number;
}

export interface ExternalKnowledgeSource {
  sourceId?: string;
  title: string;
  url?: string;
  domain: string;
  sourceType: string;
  citedInAnswer: boolean;
  consulted: boolean;
  verificationStatus: string;
  freshnessMetadataStatus: string;
  publishedAt?: string;
  sourceUpdatedAt?: string;
  fetchedAt?: string;
}

export interface ExternalRequirement {
  requirement: string;
  freshnessClass: string;
  searchEligible: boolean;
  externalSearchStatus: string;
  reviewStatus: string;
  freshnessValidation: string;
}

export interface ExternalKnowledgeRecord {
  id: number;
  query: string;
  rewrittenQuery?: string;
  missingRequirements: string[];
  recoveryQueries: string[];
  externalStatus: string;
  externalModel?: string;
  answerGenerated: boolean;
  sourceCount: number;
  citedSourceCount: number;
  ingestionStatus: string;
  status: string;
  sources: ExternalKnowledgeSource[];
  requirements: ExternalRequirement[];
  createdAt: string;
  updatedAt: string;
}

export interface ExternalKnowledgeDashboard {
  summary: ExternalKnowledgeSummary;
  statusCounts: Record<string, number>;
  records: ExternalKnowledgeRecord[];
}
