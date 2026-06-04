import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ModelService } from './model';

describe('ModelService', () => {
  let service: ModelService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), ModelService],
    });
    service = TestBed.inject(ModelService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('listModels GETs /api/models and unwraps data', () => {
    const models = {
      checkpoints: [{ filename: 'a.safetensors', base_dir: '/m', size_bytes: 1, modified_at: 0 }],
    };
    let result: unknown;
    service.listModels().subscribe((r) => (result = r));
    http.expectOne('/tiny-model-manager/api/models').flush({ success: true, data: models });
    expect(result).toEqual(models);
  });

  it('deleteModel sends DELETE to correct URL', () => {
    service.deleteModel('loras', 'my.safetensors').subscribe();
    http.expectOne('/tiny-model-manager/api/models/loras/my.safetensors');
  });

  it('getMetadata GETs metadata URL and unwraps data', () => {
    const meta = {
      description: 'A lora',
      trigger_words: ['word'],
      tags: [],
      media: [],
      base_model: 'SDXL 1.0',
      source_platform: 'civitai',
      source_url: 'https://civitai.com/models/1',
    };
    let result: unknown;
    service.getMetadata('loras', 'my.safetensors').subscribe((r) => (result = r));
    http
      .expectOne('/tiny-model-manager/api/models/loras/my.safetensors/metadata')
      .flush({ success: true, data: meta });
    expect(result).toEqual(meta);
  });

  it('updateMetadata sends PUT', () => {
    service.updateMetadata('loras', 'my.safetensors', { description: 'new' }).subscribe();
    const req = http.expectOne('/tiny-model-manager/api/models/loras/my.safetensors/metadata');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ description: 'new' });
  });

  it('refetchMetadata POSTs to /refetch and unwraps fresh metadata', () => {
    const meta = {
      description: '',
      trigger_words: [],
      tags: [],
      media: [],
      base_model: '',
      source_platform: '',
      source_url: '',
    };
    let result: unknown;
    service.refetchMetadata('loras', 'my.safetensors').subscribe((r) => (result = r));
    http
      .expectOne('/tiny-model-manager/api/models/loras/my.safetensors/refetch')
      .flush({ success: true, data: meta });
    expect(result).toEqual({ removed: false, meta });
  });

  it('refetchMetadata reports removed when the stale record was pruned', () => {
    let result: unknown;
    service.refetchMetadata('loras', 'gone.safetensors').subscribe((r) => (result = r));
    http
      .expectOne('/tiny-model-manager/api/models/loras/gone.safetensors/refetch')
      .flush({ success: true, data: { removed: true } });
    expect(result).toEqual({ removed: true });
  });

  it('getModelTypes GETs /model-types and unwraps data', () => {
    let result: unknown;
    service.getModelTypes().subscribe((r) => (result = r));
    http
      .expectOne('/tiny-model-manager/api/model-types')
      .flush({ success: true, data: ['checkpoints', 'loras'] });
    expect(result).toEqual(['checkpoints', 'loras']);
  });

  it('moveModel POSTs to /move with new_type', () => {
    service.moveModel('checkpoints', 'f.safetensors', 'loras').subscribe();
    const req = http.expectOne('/tiny-model-manager/api/models/checkpoints/f.safetensors/move');
    expect(req.request.body).toEqual({ new_type: 'loras' });
  });

  it('refetchCatalog POSTs to catalog /refetch and unwraps the entry', () => {
    let result: unknown;
    service.refetchCatalog('huggingface', 'user/repo').subscribe((r) => (result = r));
    http
      .expectOne('/tiny-model-manager/api/catalog/huggingface/user/repo/refetch')
      .flush({ success: true, data: { id: 1, description: 'd' } });
    expect(result).toEqual({ id: 1, description: 'd' });
  });

  it('updateCatalogMetadata PUTs to catalog /metadata with the payload', () => {
    service.updateCatalogMetadata('civitai', '123', { description: 'x', tags: [] }).subscribe();
    const req = http.expectOne('/tiny-model-manager/api/catalog/civitai/123/metadata');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ description: 'x', tags: [] });
  });
});
