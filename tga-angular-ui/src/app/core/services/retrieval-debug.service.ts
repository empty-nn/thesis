import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import { RetrievalDebugRun } from '../models/retrieval.models';

type RetrievalDebugApiResponse = Omit<RetrievalDebugRun, 'createdAt'> & {
  createdAt: string;
};

@Injectable({ providedIn: 'root' })
export class RetrievalDebugService {
  private readonly http = inject(HttpClient);

  run(query: string): Promise<RetrievalDebugRun> {
    return firstValueFrom(
      this.http
        .post<RetrievalDebugApiResponse>(
          `${environment.apiBaseUrl}/retrieval/debug`,
          { query },
        )
        .pipe(
          map((response) => ({
            ...response,
            createdAt: new Date(response.createdAt),
          })),
        ),
    );
  }
}
