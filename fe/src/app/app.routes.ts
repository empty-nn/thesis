// src/app/app.routes.ts
import { Routes } from '@angular/router';
import { ChatComponent } from './components/chat/chat.component'; // Adjust path if needed

export const routes: Routes = [
  { path: '', component: ChatComponent }, // Default home route
];