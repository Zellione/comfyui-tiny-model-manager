import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { KeywordsService } from './keywords';

const API = '/tiny-model-manager/api';

describe('KeywordsService', () => {
  let service: KeywordsService;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), KeywordsService],
    });
    service = TestBed.inject(KeywordsService);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => ctrl.verify());

  it('getKeywords unwraps the data field', () => {
    const keywords = [{ id: 1, keyword: 'sdxl', base_model: 'SDXL 1.0', model_type: null }];
    let result: unknown;
    service.getKeywords().subscribe((r) => (result = r));

    const req = ctrl.expectOne(`${API}/filename-keywords`);
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: keywords });
    expect(result).toEqual(keywords);
  });

  it('createKeyword posts the payload and unwraps the id', () => {
    let result: unknown;
    service.createKeyword('pony', 'Pony', 'loras').subscribe((r) => (result = r));

    const req = ctrl.expectOne(`${API}/filename-keywords`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ keyword: 'pony', base_model: 'Pony', model_type: 'loras' });
    req.flush({ success: true, data: { id: 7 } });
    expect(result).toEqual({ id: 7 });
  });

  it('updateKeyword puts to the id route', () => {
    let completed = false;
    service.updateKeyword(7, 'flux', null, null).subscribe({ complete: () => (completed = true) });

    const req = ctrl.expectOne(`${API}/filename-keywords/7`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ keyword: 'flux', base_model: null, model_type: null });
    req.flush(null);
    expect(completed).toBe(true);
  });

  it('deleteKeyword deletes the id route', () => {
    let completed = false;
    service.deleteKeyword(9).subscribe({ complete: () => (completed = true) });

    const req = ctrl.expectOne(`${API}/filename-keywords/9`);
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
    expect(completed).toBe(true);
  });
});
