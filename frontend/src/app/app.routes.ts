import { Routes } from '@angular/router';
import { Models } from './pages/models/models';
import { Download } from './pages/download/download';
import { ModelDetail } from './pages/model-detail/model-detail';

export const routes: Routes = [
  { path: '', redirectTo: 'models', pathMatch: 'full' },
  { path: 'models', component: Models },
  { path: 'models/:type/:path', component: ModelDetail },
  { path: 'download', component: Download },
];
