import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
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

@Component({
  selector: 'app-retrieval-debug-page',
  imports: [
    FormsModule,
    TableModule,
    TabsModule,
    TagModule,
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

  constructor() {
    void this.run();
  }

  protected async run(): Promise<void> {
    const value = this.query().trim();

    if (!value || this.loading()) {
      return;
    }

    this.loading.set(true);
    this.selectedChunk.set(null);

    try {
      this.runResult.set(await this.retrieval.run(value));
    } catch (error) {
      console.error(error);
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
}
