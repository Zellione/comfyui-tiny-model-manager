import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { CivitaiService } from './civitai';

describe('CivitaiService', () => {
  let service: CivitaiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), CivitaiService],
    });
    service = TestBed.inject(CivitaiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('search GETs civitai search endpoint', () => {
    let result: unknown;
    service.search({ q: 'lora' }).subscribe((r) => (result = r));
    const req = http.expectOne((r) => r.url.includes('/api/search/civitai'));
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: { items: [{ id: 1 }], metadata: {} } });
    expect((result as { items: unknown[] }).items).toHaveLength(1);
  });

  it('search includes cursor when query and cursor are both set', () => {
    service.search({ q: 'lora', page: 1, cursor: 'abc123' }).subscribe();
    const req = http.expectOne((r) => r.url.includes('/api/search/civitai'));
    expect(req.request.params.get('cursor')).toBe('abc123');
    req.flush({ success: true, data: { items: [], metadata: {} } });
  });

  it('search includes page when cursor is empty', () => {
    service.search({ q: 'lora', page: 3, cursor: '' }).subscribe();
    const req = http.expectOne((r) => r.url.includes('/api/search/civitai'));
    expect(req.request.params.get('page')).toBe('3');
    req.flush({ success: true, data: { items: [], metadata: {} } });
  });

  it('getVersions GETs versions endpoint', () => {
    service.getVersions(42).subscribe();
    http.expectOne('/tiny-model-manager/api/civitai/versions/42').flush({
      success: true,
      data: { versions: [], model_type: 'loras' },
    });
  });

  it('resolveDirectLink GETs resolve endpoint', () => {
    service.resolveDirectLink(99).subscribe();
    http.expectOne('/tiny-model-manager/api/civitai/resolve/99').flush({
      success: true,
      data: { filename: 'f.safetensors', model_type: 'loras', size_kb: 1, image_urls: [] },
    });
  });
});
