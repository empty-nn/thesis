import { Component, computed, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { MarkdownComponent } from 'ngx-markdown';
import {
  LucideDatabase,
  LucideExternalLink,
  LucideSearch,
  LucideTimer,
  LucideX,
} from '@lucide/angular';
import { TableModule } from 'primeng/table';
import { TabsModule } from 'primeng/tabs';
import { TagModule } from 'primeng/tag';

import {
  RetrievalChunk,
  RetrievalDebugRun,
  RetrievalStage,
} from '../../core/models/retrieval.models';
import { RetrievalDebugService } from '../../core/services/retrieval-debug.service';
import { PreprocessingDetailsComponent } from './preprocessing-details.component';

@Component({
  selector: 'app-retrieval-debug-page',
  imports: [
    FormsModule,
    MarkdownComponent,
    TableModule,
    TabsModule,
    TagModule,
    PreprocessingDetailsComponent,
    LucideDatabase,
    LucideExternalLink,
    LucideSearch,
    LucideTimer,
    LucideX,
  ],
  templateUrl: './retrieval-debug-page.component.html',
})
export class RetrievalDebugPageComponent {
  private readonly retrieval = inject(RetrievalDebugService);

  protected readonly stageTabs: {
    value: RetrievalStage;
    label: string;
  }[] = [
    { value: 'vector', label: 'Vector' },
    { value: 'bm25', label: 'BM25' },
    { value: 'hybrid', label: 'Hybrid' },
    { value: 'rerank', label: 'Rerank' },
    { value: 'final', label: 'Final' },
  ];

  protected readonly query = signal(
    'What are the best things to do around Hoan Kiem Lake?',
  );
  protected readonly loading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly runResult = signal<RetrievalDebugRun | null>(null);
  protected readonly activeStage = signal<RetrievalStage>('vector');
  protected readonly selectedChunk = signal<RetrievalChunk | null>(null);

  protected readonly currentChunks = computed(() => {
    const result = this.runResult();
    return result?.stages[this.activeStage()].chunks ?? [];
  });

  protected readonly currentStageInfo = computed(() => {
    const result = this.runResult();
    return result?.stages[this.activeStage()] ?? null;
  });

  protected readonly pipelineSteps = computed(() => {
    const result = this.runResult();

    if (!result) {
      return [];
    }

    const diagnostics = result.diagnostics;

    return [
      {
        label: 'Query rewrite',
        durationMs: diagnostics.rewriteDurationMs,
      },
      {
        label: 'Query parser',
        durationMs: diagnostics.parseDurationMs,
      },
      {
        label: 'User memory',
        durationMs: diagnostics.memoryDurationMs,
      },
      {
        label: 'Build filters',
        durationMs: diagnostics.filterDurationMs,
      },
      {
        label: 'Vector',
        durationMs: result.stages.vector.durationMs,
        stage: 'vector' as RetrievalStage,
      },
      {
        label: 'BM25',
        durationMs: result.stages.bm25.durationMs,
        stage: 'bm25' as RetrievalStage,
      },
      {
        label: 'Hybrid fusion',
        durationMs: result.stages.hybrid.durationMs,
        stage: 'hybrid' as RetrievalStage,
      },
      {
        label: 'Cross-encoder',
        durationMs: result.stages.rerank.durationMs,
        stage: 'rerank' as RetrievalStage,
      },
      {
        label: 'Final evidence',
        durationMs: result.stages.final.durationMs,
        stage: 'final' as RetrievalStage,
      },
      {
        label: 'LLM answer',
        durationMs: diagnostics.generationDurationMs,
      },
    ];
  });

  constructor() {
    void this.run();
  }

  protected async run(): Promise<void> {
    const value = this.query().trim();

    if (!value || this.loading()) {
      return;
    }

    this.loading.set(true);
    this.errorMessage.set(null);
    this.selectedChunk.set(null);

    try {
      this.runResult.set(await this.retrieval.run(value));
    } catch (error) {
      console.error(error);
      this.errorMessage.set(this.describeError(error));
    } finally {
      this.loading.set(false);
    }
  }

  protected selectStage(value: string | number | undefined): void {
    if (
      value === 'vector' ||
      value === 'bm25' ||
      value === 'hybrid' ||
      value === 'rerank' ||
      value === 'final'
    ) {
      this.activeStage.set(value);
      this.selectedChunk.set(null);
    }
  }

  protected scoreLabel(chunk: RetrievalChunk): string {
    if (this.activeStage() === 'bm25') {
      return chunk.score.toFixed(2);
    }

    return chunk.score.toFixed(3);
  }

  protected openSource(url?: string): void {
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  }

  private describeError(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const detail = error.error?.detail;

      if (typeof detail === 'string') {
        return detail;
      }

      if (error.status === 0) {
        return 'Cannot reach FastAPI at http://localhost:8000. Start the backend and try again.';
      }

      return `Backend request failed (${error.status} ${error.statusText}).`;
    }

    return 'Retrieval failed unexpectedly. Check the browser console and backend logs.';
  }
}
