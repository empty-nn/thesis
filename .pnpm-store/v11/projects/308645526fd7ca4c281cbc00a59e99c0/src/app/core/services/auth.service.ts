import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AuthUser,
  GoogleLoginResponse,
} from '../models/auth.models';

const STORAGE_KEY = 'tga.auth.user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  readonly currentUser = signal<AuthUser | null>(this.readStoredUser());
  private readonly sessionPromise: Promise<void>;

  constructor() {
    this.sessionPromise = this.restoreSession();
  }

  async isAuthenticated(): Promise<boolean> {
    await this.sessionPromise;
    return this.currentUser() !== null;
  }

  async loginWithGoogle(credential: string): Promise<GoogleLoginResponse> {
    const response = await firstValueFrom(
      this.http.post<GoogleLoginResponse>(
        `${environment.apiBaseUrl}/auth/google`,
        { credential },
        { withCredentials: true },
      ),
    );

    this.currentUser.set(response.user);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(response.user));
    return response;
  }

  async logout(): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(
          `${environment.apiBaseUrl}/auth/logout`,
          {},
          { withCredentials: true },
        ),
      );
    } finally {
      this.clearLocalUser();
    }
  }

  private async restoreSession(): Promise<void> {
    try {
      const response = await firstValueFrom(
        this.http.get<{ user: AuthUser }>(
          `${environment.apiBaseUrl}/auth/me`,
          { withCredentials: true },
        ),
      );
      this.currentUser.set(response.user);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(response.user));
    } catch {
      this.clearLocalUser();
    }
  }

  private clearLocalUser(): void {
    this.currentUser.set(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  private readStoredUser(): AuthUser | null {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return value ? (JSON.parse(value) as AuthUser) : null;
    } catch {
      return null;
    }
  }
}
