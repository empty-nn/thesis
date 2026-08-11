import { Component, computed, input } from '@angular/core';

import { RetrievalDebugDiagnostics } from '../../core/models/retrieval.models';

@Component({
  selector: 'app-preprocessing-details',
  templateUrl: './preprocessing-details.component.html',
})
export class PreprocessingDetailsComponent {
  readonly diagnostics = input.required<RetrievalDebugDiagnostics>();

  protected readonly parsedQueryJson = computed(() =>
    JSON.stringify(this.diagnostics().parsedQuery, null, 2),
  );

  protected readonly userMemoryJson = computed(() =>
    JSON.stringify(this.diagnostics().userMemory, null, 2),
  );
}
