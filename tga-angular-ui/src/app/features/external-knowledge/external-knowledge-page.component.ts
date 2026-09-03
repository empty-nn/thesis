import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import {
  LucideCheckCircle2,
  LucideCircleAlert,
  LucideClock3,
  LucideDatabaseZap,
  LucideExternalLink,
  LucideGlobe2,
  LucideRefreshCw,
  LucideSearch,
  LucideShieldCheck,
  LucideSparkles,
} from '@lucide/angular';

import {
  ExternalKnowledgeRecord,
  ExternalKnowledgeSource,
} from '../../core/models/external-knowledge.models';
import { ExternalKnowledgeService } from '../../core/services/external-knowledge.service';

type QueueFilter = 'all' | 'completed' | 'pending_review' | 'stable';

interface SourceSummary extends ExternalKnowledgeSource {
  recordCount: number;
  citationCount: number;
}

@Component({
  selector: 'app-external-knowledge-page',
  imports: [
    DatePipe,
    LucideCheckCircle2,
    LucideCircleAlert,
    LucideClock3,
    LucideDatabaseZap,
    LucideExternalLink,
    LucideGlobe2,
    LucideRefreshCw,
    LucideSearch,
    LucideShieldCheck,
    LucideSparkles,
  ],
  templateUrl: './external-knowledge-page.component.html',
})
export class ExternalKnowledgePageComponent {
  protected readonly externalKnowledge = inject(ExternalKnowledgeService);
  protected readonly activeFilter = signal<QueueFilter>('all');

  protected readonly filteredRecords = computed(() => {
    const records = this.externalKnowledge.dashboard()?.records ?? [];
    switch (this.activeFilter()) {
      case 'completed':
        return records.filter((item) => item.externalStatus === 'completed');
      case 'pending_review':
        return records.filter((item) => item.ingestionStatus === 'pending_review');
      case 'stable':
        return records.filter(
          (item) => item.externalStatus === 'skipped_no_time_sensitive_requirements',
        );
      default:
        return records;
    }
  });

  protected readonly sourceSummaries = computed<SourceSummary[]>(() => {
    const records = this.externalKnowledge.dashboard()?.records ?? [];
    const sources = new Map<string, SourceSummary>();
    for (const record of records) {
      for (const source of record.sources) {
        const key = source.url || `${source.domain}:${source.title}`;
        const existing = sources.get(key);
        if (existing) {
          existing.recordCount += 1;
          existing.citationCount += Number(source.citedInAnswer);
        } else {
          sources.set(key, {
            ...source,
            recordCount: 1,
            citationCount: Number(source.citedInAnswer),
          });
        }
      }
    }
    return [...sources.values()]
      .sort(
        (a, b) =>
          b.citationCount - a.citationCount || b.recordCount - a.recordCount,
      )
      .slice(0, 10);
  });

  constructor() {
    void this.externalKnowledge.load();
  }

  protected setFilter(filter: QueueFilter): void {
    this.activeFilter.set(filter);
  }

  protected statusLabel(status: string): string {
    const labels: Record<string, string> = {
      completed: 'Web evidence used',
      skipped_no_time_sensitive_requirements: 'Stable gap',
      clarification_required: 'Needs clarification',
      disabled: 'Search disabled',
      unavailable: 'Search unavailable',
      not_attempted: 'Awaiting recovery',
    };
    return labels[status] ?? status.replaceAll('_', ' ');
  }

  protected statusClass(record: ExternalKnowledgeRecord): string {
    if (record.externalStatus === 'completed') {
      return 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300';
    }
    if (record.externalStatus === 'clarification_required') {
      return 'border-amber-400/20 bg-amber-400/10 text-amber-300';
    }
    if (record.externalStatus === 'skipped_no_time_sensitive_requirements') {
      return 'border-sky-400/20 bg-sky-400/10 text-sky-300';
    }
    return 'border-white/10 bg-white/5 text-zinc-400';
  }

  protected sourceTypeLabel(sourceType: string): string {
    const labels: Record<string, string> = {
      official_government: 'Official',
      academic: 'Academic',
      real_time_feed: 'Live feed',
      open_web: 'Open web',
    };
    return labels[sourceType] ?? sourceType.replaceAll('_', ' ');
  }
}
