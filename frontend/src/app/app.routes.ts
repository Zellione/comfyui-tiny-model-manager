import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { Models } from './pages/models/models';
import { Download } from './pages/download/download';
import { ModelDetail } from './pages/model-detail/model-detail';
import { CatalogDetail } from './pages/catalog-detail/catalog-detail';
import { Settings } from './pages/settings/settings';

export const routes: Routes = [
  { path: '', redirectTo: 'models', pathMatch: 'full' },
  { path: 'models', component: Models },
  // Two segments — cannot collide with the three-segment model-detail route below.
  { path: 'models/:platform', component: CatalogDetail },
  { path: 'models/:type/:path', component: ModelDetail },
  { path: 'download', component: Download },
  { path: 'settings', component: Settings },
  // Legacy paths from when this tab was called "Catalog"; kept so old links and bookmarks work.
  { path: 'catalog', redirectTo: 'models', pathMatch: 'full' },
  {
    // A string redirectTo would drop the query string, and the detail page reads ?pageId=.
    path: 'catalog/:platform',
    redirectTo: (r) =>
      inject(Router).createUrlTree(['/models', r.params['platform']], {
        queryParams: r.queryParams,
      }),
  },
];
