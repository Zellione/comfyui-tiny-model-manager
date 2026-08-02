import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { WorkflowStoreService } from './workflow-store';

describe('WorkflowStoreService', () => {
  let service: WorkflowStoreService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), WorkflowStoreService],
    });
    service = TestBed.inject(WorkflowStoreService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('search GETs the workflow search endpoint and unwraps data', () => {
    let result: { items: unknown[]; installed_version_ids: string[] } | undefined;
    service.search({ q: 'flux' }).subscribe((r) => (result = r));
    const req = http.expectOne((r) => r.url.includes('/api/workflows/search'));
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('q')).toBe('flux');
    req.flush({
      success: true,
      data: { items: [{ id: 1 }], metadata: {}, installed_version_ids: ['7'] },
    });
    expect(result?.items).toHaveLength(1);
    expect(result?.installed_version_ids).toEqual(['7']);
  });

  it('search defaults missing fields to empty values', () => {
    let result: { items: unknown[]; installed_version_ids: string[] } | undefined;
    service.search({ q: '' }).subscribe((r) => (result = r));
    http
      .expectOne((r) => r.url.includes('/api/workflows/search'))
      .flush({
        success: true,
        data: {},
      });
    expect(result?.items).toEqual([]);
    expect(result?.installed_version_ids).toEqual([]);
  });

  it('search sends the cursor instead of the page when set', () => {
    service.search({ q: 'x', page: 2, cursor: 'abc' }).subscribe();
    const req = http.expectOne((r) => r.url.includes('/api/workflows/search'));
    expect(req.request.params.get('cursor')).toBe('abc');
    expect(req.request.params.get('page')).toBeNull();
    req.flush({ success: true, data: { items: [], metadata: {}, installed_version_ids: [] } });
  });

  it('search sends filter params', () => {
    service
      .search({ q: 'x', baseModel: 'Flux.1 D', sort: 'Newest', period: 'Month', tags: ['a', 'b'] })
      .subscribe();
    const req = http.expectOne((r) => r.url.includes('/api/workflows/search'));
    expect(req.request.params.get('base_model')).toBe('Flux.1 D');
    expect(req.request.params.get('sort')).toBe('Newest');
    expect(req.request.params.get('period')).toBe('Month');
    expect(req.request.params.get('tags')).toBe('a,b');
    req.flush({ success: true, data: { items: [], metadata: {}, installed_version_ids: [] } });
  });

  it('download POSTs the model and version ids as strings', () => {
    let result: { entry_id: number } | undefined;
    service.download(123, 456).subscribe((r) => (result = r));
    const req = http.expectOne('/tiny-model-manager/api/workflows/download');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ model_id: '123', version_id: '456' });
    req.flush({ success: true, data: { entry_id: 1, workflows: [] } });
    expect(result?.entry_id).toBe(1);
  });

  it('list GETs the entries and unwraps data', () => {
    let result: unknown[] | undefined;
    service.list().subscribe((r) => (result = r));
    http
      .expectOne('/tiny-model-manager/api/workflows')
      .flush({ success: true, data: [{ id: 1, items: [], media: [] }] });
    expect(result).toHaveLength(1);
  });

  it('list falls back to an empty array', () => {
    let result: unknown[] | undefined;
    service.list().subscribe((r) => (result = r));
    http.expectOne('/tiny-model-manager/api/workflows').flush({ success: true });
    expect(result).toEqual([]);
  });

  it('deleteEntry DELETEs the entry', () => {
    service.deleteEntry(5).subscribe();
    const req = http.expectOne('/tiny-model-manager/api/workflows/5');
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });

  it('exportWorkflow POSTs to the export endpoint', () => {
    let result: { path: string } | undefined;
    service.exportWorkflow(9).subscribe((r) => (result = r));
    const req = http.expectOne('/tiny-model-manager/api/workflows/9/export');
    expect(req.request.method).toBe('POST');
    req.flush({ success: true, data: { path: '/user/default/workflows/a.json' } });
    expect(result?.path).toContain('a.json');
  });

  it('openInComfy POSTs to the open endpoint', () => {
    let result: { id: string } | undefined;
    service.openInComfy(9).subscribe((r) => (result = r));
    const req = http.expectOne('/tiny-model-manager/api/workflows/9/open');
    expect(req.request.method).toBe('POST');
    req.flush({ success: true, data: { id: 'uuid-1' } });
    expect(result?.id).toBe('uuid-1');
  });

  it('fileUrl points at the raw graph endpoint', () => {
    expect(service.fileUrl(12)).toBe('/tiny-model-manager/api/workflows/12/file');
  });
});
