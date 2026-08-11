import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/google-auth-page.component').then(
        (module) => module.GoogleAuthPageComponent,
      ),
  },
  {
    path: 'chat/:conversationId',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/chat/chat-page.component').then(
        (module) => module.ChatPageComponent,
      ),
  },
  {
    path: 'chat',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/chat/chat-page.component').then(
        (module) => module.ChatPageComponent,
      ),
  },
  {
    path: 'retrieval-debug',
    canActivate: [authGuard],
    loadComponent: () =>
      import(
        './features/retrieval-debug/retrieval-debug-page.component'
      ).then((module) => module.RetrievalDebugPageComponent),
  },
  {
    path: '',
    pathMatch: 'full',
    redirectTo: 'chat',
  },
  {
    path: '**',
    redirectTo: 'chat',
  },
];
