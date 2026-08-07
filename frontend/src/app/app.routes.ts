import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'models', pathMatch: 'full' },
  { path: 'models', loadComponent: () => import('./pages/models/models').then((m) => m.Models) },
  // Two segments — cannot collide with the three-segment model-detail route below.
  {
    path: 'models/:platform',
    loadComponent: () =>
      import('./pages/catalog-detail/catalog-detail').then((m) => m.CatalogDetail),
  },
  {
    path: 'models/:type/:path',
    loadComponent: () => import('./pages/model-detail/model-detail').then((m) => m.ModelDetail),
  },
  // Single segment — no collision with the 2-vs-3-segment models/… discrimination above.
  {
    path: 'workflows',
    loadComponent: () => import('./pages/workflows/workflows').then((m) => m.Workflows),
  },
  { path: 'images', loadComponent: () => import('./pages/images/images').then((m) => m.Images) },
  {
    path: 'download',
    loadComponent: () => import('./pages/download/download').then((m) => m.Download),
  },
  {
    path: 'settings',
    loadComponent: () => import('./pages/settings/settings').then((m) => m.Settings),
  },
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
