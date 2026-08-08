import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ModelImportService } from './model-import';

describe('ModelImportService', () => {
  let service: ModelImportService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ModelImportService, provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ModelImportService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('posts the path to start a scan', () => {
    let result: unknown;
    service.startScan('/mnt/other/models').subscribe((r) => (result = r));

    const req = httpMock.expectOne('/tiny-model-manager/api/import/scan');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ path: '/mnt/other/models' });
    req.flush({ success: true, data: { job_id: 'j1', source_root: '/mnt/other/models' } });

    expect(result).toEqual({ job_id: 'j1', source_root: '/mnt/other/models' });
  });

  it('unwraps the scan job payload', () => {
    let state: unknown;
    service.pollScan('j1').subscribe((s) => (state = s));

    const req = httpMock.expectOne('/tiny-model-manager/api/import/scan/j1');
    expect(req.request.method).toBe('GET');
    req.flush({
      success: true,
      data: { id: 'j1', state: 'done', progress: 100, files: [], imported: [], failed: [] },
    });

    expect((state as { state: string }).state).toBe('done');
  });

  it('posts the source root and selection to start an import', () => {
    const files = [{ model_type: 'loras', filename: 'a.safetensors', file_hash: 'ff' }];
    service.startImport('/mnt/other/models', files).subscribe();

    const req = httpMock.expectOne('/tiny-model-manager/api/import/start');
    expect(req.request.body).toEqual({ source_root: '/mnt/other/models', files });
    req.flush({ success: true, data: { job_id: 'j2' } });
  });

  it('polls an import job', () => {
    service.pollJob('j2').subscribe();
    const req = httpMock.expectOne('/tiny-model-manager/api/import/jobs/j2');
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: { id: 'j2', state: 'running', progress: 50 } });
  });

  it('cancels a job', () => {
    service.cancelJob('j2').subscribe();
    const req = httpMock.expectOne('/tiny-model-manager/api/import/jobs/j2/cancel');
    expect(req.request.method).toBe('POST');
    req.flush({ success: true, data: { cancelled: true } });
  });
});
