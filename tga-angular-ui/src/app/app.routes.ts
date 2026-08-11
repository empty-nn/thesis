import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: 'chat',
    loadComponent: () =>
      import('./features/chat/chat-page.component').then(
        (module) => module.ChatPageComponent,
      ),
  },
  {
    path: 'retrieval-debug',
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
