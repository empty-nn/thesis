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
    path: 'external-knowledge',
    canActivate: [authGuard],
    loadComponent: () =>
      import(
        './features/external-knowledge/external-knowledge-page.component'
      ).then((module) => module.ExternalKnowledgePageComponent),
  },
  {
    path: 'data-building',
    canActivate: [authGuard],
    loadComponent: () => import('./features/data-building/data-building-page.component')
      .then((module) => module.DataBuildingPageComponent),
  },
  {
    path: 'retrieval-debug',
    redirectTo: 'external-knowledge',
  },
  {
    path: 'memory',
    redirectTo: 'external-knowledge',
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
