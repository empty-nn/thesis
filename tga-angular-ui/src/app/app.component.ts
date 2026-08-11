import { Component, signal } from '@angular/core';
import {
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import {
  LucideBot,
  LucideDatabase,
  LucideMenu,
  LucideMessageSquare,
  LucidePlus,
  LucideX,
} from '@lucide/angular';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    LucideBot,
    LucideDatabase,
    LucideMenu,
    LucideMessageSquare,
    LucidePlus,
    LucideX,
  ],
  templateUrl: './app.component.html',
})
export class AppComponent {
  protected readonly mobileSidebarOpen = signal(false);

  protected closeSidebar(): void {
    this.mobileSidebarOpen.set(false);
  }
}
