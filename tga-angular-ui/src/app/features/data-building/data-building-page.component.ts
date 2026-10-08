import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';

interface Extraction {
  document_type: 'html' | 'pdf'; source_location: string; extraction_method: string;
  raw_markdown: string; title: string; file_hash: string | null;
}
interface Chunk {
  chunk_index: number; chunk_text: string; section_heading: string | null;
  word_count: number; char_count: number;
}
interface SavedDocument { document_id: string; saved_chunks: number; status: string; }

@Component({
  selector: 'app-data-building-page',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './data-building-page.component.html',
})
export class DataBuildingPageComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiBaseUrl}/data-building`;
  readonly busy = signal('');
  readonly error = signal('');
  readonly notice = signal('');
  readonly canStore = signal(false);
  readonly chunks = signal<Chunk[]>([]);
  readonly saved = signal<SavedDocument | null>(null);
  sourceType: 'html' | 'pdf' = 'html';
  url = '';
  method = 'trafilatura';
  file: File | null = null;
  extraction: Extraction | null = null;
  rawMarkdown = '';
  cleanedMarkdown = '';
  keepPictureText = true;
  separatePictureText = true;
  minPictureTextChars = 80;
  chunkSize = 1200;
  chunkOverlap = 150;
  metadata = { title: '', country: '', city: '', province: '', language: 'english' };
  confirmSave = false;

  async ngOnInit(): Promise<void> {
    try {
      const capabilities = await firstValueFrom(this.http.get<{ can_store: boolean }>(
        `${this.base}/capabilities`, { withCredentials: true }));
      this.canStore.set(capabilities.can_store);
    } catch {
      this.error.set('Data Building could not connect. Refresh the page or sign in again.');
    }
  }

  selectFile(event: Event): void {
    this.file = (event.target as HTMLInputElement).files?.[0] ?? null;
    this.invalidateSource();
    if (this.file && this.file.size > 8 * 1024 * 1024) {
      this.error.set('PDF must be no larger than 8 MB.');
      this.file = null;
    }
  }

  invalidateSource(): void {
    this.extraction = null;
    this.rawMarkdown = '';
    this.cleanedMarkdown = '';
    this.invalidateChunks();
    this.notice.set('');
    this.error.set('');
  }

  invalidateClean(): void {
    this.cleanedMarkdown = '';
    this.invalidateChunks();
  }

  invalidateChunks(): void {
    this.chunks.set([]);
    this.saved.set(null);
    this.confirmSave = false;
  }

  async extract(): Promise<void> {
    await this.run('Extracting source', async () => {
      let result: Extraction;
      if (this.sourceType === 'pdf') {
        if (!this.file) throw new Error('Choose a PDF first.');
        const form = new FormData();
        form.append('file', this.file);
        result = await this.post<Extraction>('extract-pdf', form);
      } else {
        result = await this.post<Extraction>('extract-url', { url: this.url.trim(), method: this.method });
      }
      this.extraction = result;
      this.rawMarkdown = result.raw_markdown;
      this.metadata.title = result.title;
      this.invalidateClean();
      this.notice.set('Extraction complete. Review or edit the raw Markdown before cleaning.');
    });
  }

  async clean(): Promise<void> {
    await this.run('Cleaning Markdown', async () => {
      const result = await this.post<{ cleaned_markdown: string }>('clean', {
        markdown: this.rawMarkdown, keep_picture_text: this.keepPictureText,
        separate_picture_text: this.separatePictureText, min_picture_text_chars: this.minPictureTextChars,
      });
      this.cleanedMarkdown = result.cleaned_markdown;
      this.invalidateChunks();
      this.notice.set('Cleaning complete. Review the text and source metadata, then preview chunks.');
    });
  }

  private preparedPayload() {
    return { cleaned_markdown: this.cleanedMarkdown, chunk_size: this.chunkSize,
      chunk_overlap: this.chunkOverlap, metadata: { ...this.metadata } };
  }

  async prepare(): Promise<void> {
    await this.run('Preparing chunks', async () => {
      const result = await this.post<{ chunks: Chunk[] }>('prepare', this.preparedPayload());
      this.chunks.set(result.chunks);
      this.saved.set(null);
      this.confirmSave = false;
      this.notice.set(`${result.chunks.length} chunks ready. Nothing has been written to the database yet.`);
    });
  }

  async store(): Promise<void> {
    if (!this.extraction || !this.canStore() || !this.confirmSave || !this.chunks().length || this.saved()) return;
    const extraction = this.extraction;
    await this.run('Embedding and saving to Neon', async () => {
      const result = await this.post<SavedDocument>('store', {
        ...this.preparedPayload(), document_type: extraction.document_type,
        source_location: extraction.source_location, extraction_method: extraction.extraction_method,
        raw_markdown: this.rawMarkdown, file_hash: extraction.file_hash,
      });
      this.saved.set(result);
      this.notice.set(`Saved ${result.saved_chunks} chunks. This document is now available for database retrieval.`);
    });
  }

  reset(): void {
    this.invalidateSource();
    this.metadata = { title: '', country: '', city: '', province: '', language: 'english' };
  }

  private post<T>(path: string, body: unknown): Promise<T> {
    return firstValueFrom(this.http.post<T>(`${this.base}/${path}`, body, { withCredentials: true }));
  }

  private async run(label: string, action: () => Promise<void>): Promise<void> {
    if (this.busy()) return;
    this.busy.set(label);
    this.error.set('');
    this.notice.set('');
    try { await action(); }
    catch (error) {
      if (error instanceof HttpErrorResponse) {
        const detail: unknown = error.error?.detail;
        this.error.set(typeof detail === 'string' ? detail :
          error.status === 422 ? 'Check the inputs: text limit 200,000 characters; overlap must be smaller than chunk size.' :
          'Request failed. Check your connection and sign-in. If a save timed out, retry: duplicates are safely rejected.');
      } else this.error.set(error instanceof Error ? error.message : 'Processing failed.');
    } finally { this.busy.set(''); }
  }
}
