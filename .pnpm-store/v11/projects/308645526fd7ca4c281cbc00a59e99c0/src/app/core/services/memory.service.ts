import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import { UserMemoryItem } from '../models/memory.models';

@Injectable({ providedIn: 'root' })
export class MemoryService {
  private readonly http = inject(HttpClient);
  readonly memories = signal<UserMemoryItem[]>([]);
  readonly loading = signal(false);

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.memories.set(
        await firstValueFrom(
          this.http.get<UserMemoryItem[]>(
            `${environment.apiBaseUrl}/memories`,
            { withCredentials: true },
          ),
        ),
      );
    } finally {
      this.loading.set(false);
    }
  }

  async remove(id: number): Promise<void> {
    await firstValueFrom(
      this.http.delete(
        `${environment.apiBaseUrl}/memories/${id}`,
        { withCredentials: true },
      ),
    );
    this.memories.update((items) => items.filter((item) => item.id !== id));
  }
}
