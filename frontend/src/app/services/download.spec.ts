import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { DownloadService, DownloadTask } from './download';

function makeTask(overrides: Partial<DownloadTask> = {}): DownloadTask {
  return {
    id: '1',
    url: 'https://example.com/m.safetensors',
    model_type: 'checkpoints',
    filename: 'm.safetensors',
    platform: 'civitai',
    source_id: '123',
    status: 'queued',
    progress: 0,
    downloaded_bytes: 0,
    total_bytes: 0,
    error: null,
    ...overrides,
  };
}

describe('DownloadService', () => {
  let service: DownloadService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), DownloadService],
    });
    service = TestBed.inject(DownloadService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('startDownload POSTs to /download and unwraps task_id', () => {
    let result: unknown;
    service
      .startDownload('https://example.com/m.safetensors', 'checkpoints', 'm.safetensors', 'civitai')
      .subscribe((r) => (result = r));
    const req = http.expectOne('/tiny-model-manager/api/download');
    expect(req.request.method).toBe('POST');
    req.flush({ success: true, data: { task_id: 'abc-123' } });
    expect(result).toEqual({ task_id: 'abc-123' });
  });

  it('startDownload sends correct payload', () => {
    service
      .startDownload(
        'https://example.com/m.safetensors',
        'loras',
        'my.safetensors',
        'huggingface',
        'user/repo',
      )
      .subscribe();
    const req = http.expectOne('/tiny-model-manager/api/download');
    expect(req.request.body).toEqual({
      url: 'https://example.com/m.safetensors',
      model_type: 'loras',
      filename: 'my.safetensors',
      platform: 'huggingface',
      source_id: 'user/repo',
    });
    req.flush({ success: true, data: { task_id: 'x' } });
  });

  it('activeTasks$ emits task list on subscribe', () => {
    const tasks = [makeTask({ status: 'downloading' })];
    let result: DownloadTask[] | undefined;
    service.activeTasks$.subscribe((r) => (result = r));

    // startWith(0) emits immediately → first HTTP request fires synchronously
    http.expectOne('/tiny-model-manager/api/download/status').flush({ success: true, data: tasks });

    expect(result).toEqual(tasks);
  });
});
