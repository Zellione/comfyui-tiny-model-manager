import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideLocationMocks } from '@angular/common/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from './app.routes';

@Component({ template: '' })
class StubPage {}

// Drive the real route table, but swap every page component for a stub so navigation
// exercises the paths and redirects without instantiating any page and its services.
const testRoutes = routes.map((r) => ('component' in r ? { ...r, component: StubPage } : r));

describe('app routes', () => {
  let router: Router;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideRouter(testRoutes), provideLocationMocks()],
    });
    router = TestBed.inject(Router);
    await RouterTestingHarness.create();
  });

  it('redirects the root path to /models', async () => {
    await router.navigateByUrl('/');
    expect(router.url).toBe('/models');
  });

  it('redirects the legacy /catalog path to /models', async () => {
    await router.navigateByUrl('/catalog');
    expect(router.url).toBe('/models');
  });

  it('redirects a legacy catalog detail link and keeps its pageId query param', async () => {
    await router.navigateByUrl('/catalog/civitai?pageId=1234');
    expect(router.url).toBe('/models/civitai?pageId=1234');
  });

  it('routes a two-segment path to the catalog detail page', async () => {
    await router.navigateByUrl('/models/civitai?pageId=1234');
    const route = router.routerState.snapshot.root.firstChild;
    expect(route?.routeConfig?.path).toBe('models/:platform');
    expect(route?.params['platform']).toBe('civitai');
  });

  it('routes the single-segment /images path without colliding with models/:platform', async () => {
    await router.navigateByUrl('/images');
    const route = router.routerState.snapshot.root.firstChild;
    expect(route?.routeConfig?.path).toBe('images');
  });

  it('routes a three-segment path to the model detail page', async () => {
    await router.navigateByUrl('/models/loras/loras%2Flocal.safetensors');
    const route = router.routerState.snapshot.root.firstChild;
    expect(route?.routeConfig?.path).toBe('models/:type/:path');
    expect(route?.params['type']).toBe('loras');
    expect(route?.params['path']).toBe('loras/local.safetensors');
  });
});
