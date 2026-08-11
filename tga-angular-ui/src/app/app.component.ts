import { Component, inject, signal } from '@angular/core';
import {
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map } from 'rxjs';
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
  private readonly router = inject(Router);
  protected readonly isLoginPage = toSignal(
    this.router.events.pipe(
      filter(
        (event): event is NavigationEnd => event instanceof NavigationEnd,
      ),
      map((event) => event.urlAfterRedirects.startsWith('/login')),
    ),
    {
      initialValue: this.router.url.startsWith('/login'),
    },
  );
  protected readonly mobileSidebarOpen = signal(false);

  protected closeSidebar(): void {
    this.mobileSidebarOpen.set(false);
  }

  protected async logout(): Promise<void> {
    await this.auth.logout();
    await this.router.navigateByUrl('/login');
  }
}
