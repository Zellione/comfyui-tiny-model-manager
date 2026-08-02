import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ImageService } from './image';

const API = '/tiny-model-manager/api';

describe('ImageService', () => {
  let service: ImageService;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ImageService, provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ImageService);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => ctrl.verify());

  describe('search', () => {
    it('unwraps data and defaults missing fields', () => {
      let result: unknown;
      service.search().subscribe((r) => (result = r));
      const req = ctrl.expectOne((r) => r.url === `${API}/images/search`);
      expect(req.request.method).toBe('GET');
      req.flush({ success: true, data: {} });
      expect(result).toEqual({ items: [], metadata: {} });
    });

    it('maps every filter onto its query parameter', () => {
      service
        .search({
          sort: 'Newest',
          period: 'Week',
          nsfw: 'None',
          baseModel: 'SDXL 1.0',
          type: 'image',
          username: 'bob',
          modelId: '7',
          cursor: 'c1',
          limit: 100,
        })
        .subscribe();
      const req = ctrl.expectOne((r) => r.url === `${API}/images/search`);
      const params = req.request.params;
      expect(params.get('sort')).toBe('Newest');
      expect(params.get('period')).toBe('Week');
      expect(params.get('nsfw')).toBe('None');
      expect(params.get('base_model')).toBe('SDXL 1.0');
      expect(params.get('type')).toBe('image');
      expect(params.get('username')).toBe('bob');
      expect(params.get('model_id')).toBe('7');
      expect(params.get('cursor')).toBe('c1');
      expect(params.get('limit')).toBe('100');
      req.flush({ success: true, data: { items: [], metadata: {} } });
    });

    it('omits period when no sort is set', () => {
      service.search({ period: 'Week' }).subscribe();
      const req = ctrl.expectOne((r) => r.url === `${API}/images/search`);
      expect(req.request.params.has('period')).toBe(false);
      req.flush({ success: true, data: { items: [], metadata: {} } });
    });
  });

  it('get fetches a single image', () => {
    let result: unknown;
    service.get(42).subscribe((r) => (result = r));
    const req = ctrl.expectOne(`${API}/images/42`);
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: { id: 42, recreatable: 'graph' } });
    expect(result).toEqual({ id: 42, recreatable: 'graph' });
  });

  describe('recreate', () => {
    it('posts and unwraps the result', () => {
      let result: { source: string; resources: unknown[] } | undefined;
      service.recreate(42).subscribe((r) => (result = r));
      const req = ctrl.expectOne(`${API}/images/42/recreate`);
      expect(req.request.method).toBe('POST');
      req.flush({
        success: true,
        data: { entry_id: 1, workflow: { id: 2 }, source: 'graph', resources: [] },
      });
      expect(result?.source).toBe('graph');
    });

    it('defaults resources to an empty array', () => {
      let result: { resources: unknown[] } | undefined;
      service.recreate(42).subscribe((r) => (result = r));
      ctrl.expectOne(`${API}/images/42/recreate`).flush({
        success: true,
        data: { entry_id: 1, workflow: { id: 2 }, source: 'params' },
      });
      expect(result?.resources).toEqual([]);
    });
  });

  describe('resolveResources', () => {
    it('posts the image id and returns the list', () => {
      let result: unknown;
      service.resolveResources(42).subscribe((r) => (result = r));
      const req = ctrl.expectOne(`${API}/images/resolve-resources`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ image_id: '42' });
      req.flush({ success: true, data: { resources: [{ name: 'a', status: 'missing' }] } });
      expect(result).toHaveLength(1);
    });

    it('defaults to an empty list', () => {
      let result: unknown;
      service.resolveResources(42).subscribe((r) => (result = r));
      ctrl.expectOne(`${API}/images/resolve-resources`).flush({ success: true, data: {} });
      expect(result).toEqual([]);
    });
  });
});
