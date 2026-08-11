import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  RetrievalChunk,
  RetrievalDebugRun,
  RetrievalStage,
  RetrievalStageResult,
} from '../models/retrieval.models';

@Injectable({ providedIn: 'root' })
export class RetrievalDebugService {
  private readonly http = inject(HttpClient);

  async run(query: string): Promise<RetrievalDebugRun> {
    if (!environment.useMockApi) {
      return firstValueFrom(
        this.http.post<RetrievalDebugRun>(
          `${environment.apiBaseUrl}/retrieval/debug`,
          { query },
        ),
      );
    }

    return this.mockRun(query);
  }

  private async mockRun(query: string): Promise<RetrievalDebugRun> {
    await new Promise((resolve) => setTimeout(resolve, 420));

    const base = this.baseChunks();

    const vector = this.stage(
      'vector',
      'Vector',
      48,
      this.rescore(base, [0.91, 0.88, 0.83, 0.77, 0.72], 'vectorScore'),
    );

    const bm25 = this.stage(
      'bm25',
      'BM25',
      31,
      this.rescore(
        [base[1], base[0], base[3], base[2], base[4]],
        [12.8, 11.7, 9.9, 8.6, 7.4],
        'bm25Score',
      ),
    );

    const hybrid = this.stage(
      'hybrid',
      'Hybrid',
      9,
      this.rescore(
        [base[0], base[1], base[2], base[3], base[4]],
        [0.94, 0.92, 0.86, 0.81, 0.76],
      ),
    );

    const rerank = this.stage(
      'rerank',
      'Rerank',
      73,
      this.rescore(
        [base[0], base[2], base[1], base[4], base[3]],
        [0.967, 0.931, 0.904, 0.862, 0.815],
        'rerankScore',
      ),
    );

    const finalStage = this.stage(
      'final',
      'Final',
      2,
      rerank.chunks.slice(0, 3).map((chunk, index) => ({
        ...chunk,
        rank: index + 1,
      })),
    );

    const stages: Record<RetrievalStage, RetrievalStageResult> = {
      vector,
      bm25,
      hybrid,
      rerank,
      final: finalStage,
    };

    return {
      query,
      createdAt: new Date(),
      totalDurationMs: Object.values(stages).reduce(
        (sum, stage) => sum + stage.durationMs,
        0,
      ),
      stages,
    };
  }

  private stage(
    stage: RetrievalStage,
    label: string,
    durationMs: number,
    chunks: RetrievalChunk[],
  ): RetrievalStageResult {
    return {
      stage,
      label,
      durationMs,
      chunks,
    };
  }

  private rescore(
    chunks: RetrievalChunk[],
    scores: number[],
    field?: 'vectorScore' | 'bm25Score' | 'rerankScore',
  ): RetrievalChunk[] {
    return chunks.map((chunk, index) => ({
      ...chunk,
      rank: index + 1,
      score: scores[index],
      ...(field ? { [field]: scores[index] } : {}),
    }));
  }

  private baseChunks(): RetrievalChunk[] {
    return [
      {
        id: 1042,
        rank: 1,
        score: 0,
        title: 'Hoan Kiem Lake and the Old Quarter',
        city: 'Hanoi',
        placeName: 'Hoan Kiem Lake',
        topic: 'Attractions',
        sourceName: 'Vietnam Tourism Guide',
        sourceUrl: 'https://example.com/hoan-kiem',
        content:
          'Hoan Kiem Lake is located in central Hanoi and is a useful starting point for exploring the Old Quarter. Visitors often combine the lake, Ngoc Son Temple, walking streets, cafes, and nearby heritage streets in one itinerary.',
        metadata: {
          country: 'Vietnam',
          province: 'Hanoi',
          city: 'Hanoi',
          placeName: 'Hoan Kiem Lake',
          placeType: 'lake',
          chunkTopic: 'attractions',
          travelStyles: ['culture', 'city break'],
          activities: ['walking', 'sightseeing'],
          suitableFor: ['first-time visitors', 'couples', 'families'],
        },
      },
      {
        id: 1088,
        rank: 2,
        score: 0,
        title: 'Hanoi Old Quarter',
        city: 'Hanoi',
        placeName: 'Old Quarter',
        topic: 'Things to do',
        sourceName: 'Local Vietnam',
        sourceUrl: 'https://example.com/old-quarter',
        content:
          'The Old Quarter is one of the most walkable areas of Hanoi. Its narrow streets contain traditional shop houses, local food, markets, cafes, temples, and easy access to Hoan Kiem Lake.',
        metadata: {
          country: 'Vietnam',
          province: 'Hanoi',
          city: 'Hanoi',
          placeName: 'Old Quarter',
          placeType: 'neighborhood',
          chunkTopic: 'things to do',
          travelStyles: ['food', 'culture', 'budget'],
          activities: ['walking', 'street food', 'shopping'],
          suitableFor: ['first-time visitors', 'solo travelers'],
        },
      },
      {
        id: 1114,
        rank: 3,
        score: 0,
        title: 'Temple of Literature',
        city: 'Hanoi',
        placeName: 'Temple of Literature',
        topic: 'Culture',
        sourceName: 'Hanoi Travel Notes',
        sourceUrl: 'https://example.com/temple-literature',
        content:
          'The Temple of Literature is a historic Confucian complex in Hanoi. The site is associated with education, traditional architecture, courtyards, stone stelae, and the history of Vietnamese scholarship.',
        metadata: {
          country: 'Vietnam',
          province: 'Hanoi',
          city: 'Hanoi',
          placeName: 'Temple of Literature',
          placeType: 'historic site',
          chunkTopic: 'culture',
          travelStyles: ['history', 'culture'],
          activities: ['sightseeing', 'photography'],
          suitableFor: ['students', 'families', 'history lovers'],
        },
      },
      {
        id: 1190,
        rank: 4,
        score: 0,
        title: 'West Lake',
        city: 'Hanoi',
        placeName: 'West Lake',
        topic: 'Relaxation',
        sourceName: 'Vietnam Destination Notes',
        sourceUrl: 'https://example.com/west-lake',
        content:
          'West Lake offers a more relaxed side of Hanoi with lakeside roads, cafes, restaurants, temples, and sunset viewpoints. It can work well after a busy day in the city center.',
        metadata: {
          country: 'Vietnam',
          province: 'Hanoi',
          city: 'Hanoi',
          placeName: 'West Lake',
          placeType: 'lake',
          chunkTopic: 'relaxation',
          travelStyles: ['slow travel', 'food'],
          activities: ['cycling', 'cafes', 'sunset'],
          suitableFor: ['couples', 'repeat visitors'],
        },
      },
      {
        id: 1255,
        rank: 5,
        score: 0,
        title: 'Hanoi Street Food',
        city: 'Hanoi',
        placeName: 'Hanoi',
        topic: 'Food',
        sourceName: 'Vietnam Food Guide',
        sourceUrl: 'https://example.com/hanoi-food',
        content:
          'Hanoi street food is spread across the central districts, with many popular choices around the Old Quarter. Common experiences include noodle dishes, grilled foods, local coffee, and small family-run shops.',
        metadata: {
          country: 'Vietnam',
          province: 'Hanoi',
          city: 'Hanoi',
          placeName: 'Hanoi',
          placeType: 'city',
          chunkTopic: 'food',
          travelStyles: ['food', 'budget'],
          activities: ['street food', 'cafes'],
          suitableFor: ['food lovers', 'solo travelers', 'groups'],
        },
      },
    ];
  }
}
