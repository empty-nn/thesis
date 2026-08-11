import { Component, inject } from '@angular/core';

import { MemoryService } from '../../core/services/memory.service';

@Component({
  selector: 'app-memory-page',
  templateUrl: './memory-page.component.html',
})
export class MemoryPageComponent {
  protected readonly memory = inject(MemoryService);

  constructor() {
    void this.memory.load();
  }
}
