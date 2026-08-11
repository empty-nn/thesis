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

  async loginWithGoogle(credential: string): Promise<GoogleLoginResponse> {
    const response = await firstValueFrom(
      this.http.post<GoogleLoginResponse>(
        `${environment.apiBaseUrl}/auth/google`,
        { credential },
      ),
    );

    this.currentUser.set(response.user);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(response.user));
    return response;
  }

  logout(): void {
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
