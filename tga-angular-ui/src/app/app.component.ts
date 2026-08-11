import { Component, inject, signal } from '@angular/core';
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
  LucideLogIn,
  LucideLogOut,
  LucidePlus,
  LucideX,
} from '@lucide/angular';
import { AuthService } from './core/services/auth.service';

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
    LucideLogIn,
    LucideLogOut,
    LucidePlus,
    LucideX,
  ],
  templateUrl: './app.component.html',
})
export class AppComponent {
  protected readonly auth = inject(AuthService);
  protected readonly mobileSidebarOpen = signal(false);

  protected closeSidebar(): void {
    this.mobileSidebarOpen.set(false);
  }
}
