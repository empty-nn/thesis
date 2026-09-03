import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import { ExternalKnowledgeDashboard } from '../models/external-knowledge.models';

@Injectable({ providedIn: 'root' })
export class ExternalKnowledgeService {
  private readonly http = inject(HttpClient);

  readonly dashboard = signal<ExternalKnowledgeDashboard | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.dashboard.set(
        await firstValueFrom(
          this.http.get<ExternalKnowledgeDashboard>(
            `${environment.apiBaseUrl}/external-knowledge`,
            { withCredentials: true },
          ),
        ),
      );
    } catch {
      this.error.set('External knowledge records could not be loaded.');
    } finally {
      this.loading.set(false);
    }
  }
}
