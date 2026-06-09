import { Routes } from '@angular/router';
import { Models } from './pages/models/models';
import { Download } from './pages/download/download';
import { ModelDetail } from './pages/model-detail/model-detail';
import { CatalogDetail } from './pages/catalog-detail/catalog-detail';
import { Settings } from './pages/settings/settings';

export const routes: Routes = [
  { path: '', redirectTo: 'catalog', pathMatch: 'full' },
  { path: 'catalog', component: Models },
  { path: 'models', redirectTo: 'catalog', pathMatch: 'full' },
  { path: 'catalog/:platform', component: CatalogDetail },
  { path: 'models/:type/:path', component: ModelDetail },
  { path: 'download', component: Download },
  { path: 'settings', component: Settings },
];
