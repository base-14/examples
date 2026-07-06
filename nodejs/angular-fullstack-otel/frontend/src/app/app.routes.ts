import { Routes } from '@angular/router';
import { Items } from './items/items';
import { About } from './about/about';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'items' },
  { path: 'items', component: Items },
  { path: 'about', component: About },
];
