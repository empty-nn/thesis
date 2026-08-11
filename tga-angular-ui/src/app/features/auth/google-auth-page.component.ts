import {
  Component,
  ElementRef,
  afterNextRender,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { environment } from '../../../environments/environment';

interface GoogleCredentialResponse {
  credential: string;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
          }): void;
          renderButton(
            element: HTMLElement,
            options: Record<string, unknown>,
          ): void;
        };
      };
    };
  }
}

@Component({
  selector: 'app-google-auth-page',
  templateUrl: './google-auth-page.component.html',
})
export class GoogleAuthPageComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly googleButton = viewChild<ElementRef<HTMLDivElement>>(
    'googleButton',
  );

  protected readonly loading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly configured =
    !environment.googleClientId.startsWith('YOUR_');

  constructor() {
    afterNextRender(() => {
      if (this.configured) {
        void this.initializeGoogleButton();
      }
    });
  }

  private async initializeGoogleButton(): Promise<void> {
    try {
      await this.loadGoogleScript();
      const element = this.googleButton()?.nativeElement;

      if (!window.google || !element) {
        throw new Error('Google Identity Services did not initialize');
      }

      window.google.accounts.id.initialize({
        client_id: environment.googleClientId,
        callback: (response) => void this.handleCredential(response),
      });
      window.google.accounts.id.renderButton(element, {
        type: 'standard',
        theme: 'filled_black',
        size: 'large',
        shape: 'pill',
        text: 'continue_with',
        width: 320,
      });
    } catch (error) {
      this.errorMessage.set(
        error instanceof Error ? error.message : 'Google Sign-In failed to load.',
      );
    }
  }

  private loadGoogleScript(): Promise<void> {
    if (window.google) {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>(
        'script[data-google-identity]',
      );

      if (existing) {
        existing.addEventListener('load', () => resolve(), { once: true });
        existing.addEventListener('error', () => reject(new Error('Unable to load Google Sign-In.')), { once: true });
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.dataset['googleIdentity'] = 'true';
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('Unable to load Google Sign-In.'));
      document.head.appendChild(script);
    });
  }

  private async handleCredential(response: GoogleCredentialResponse): Promise<void> {
    this.loading.set(true);
    this.errorMessage.set(null);

    try {
      await this.auth.loginWithGoogle(response.credential);
      await this.router.navigateByUrl('/chat');
    } catch (error) {
      const detail = error instanceof HttpErrorResponse
        ? error.error?.detail
        : null;
      this.errorMessage.set(
        typeof detail === 'string' ? detail : 'The backend could not complete Google login.',
      );
    } finally {
      this.loading.set(false);
    }
  }
}
