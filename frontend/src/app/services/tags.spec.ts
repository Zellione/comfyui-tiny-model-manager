import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TagService } from './tags';

describe('TagService', () => {
  let service: TagService;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), TagService],
    });
    service = TestBed.inject(TagService);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => ctrl.verify());

  it('searchTags sends the query param and unwraps the data field', () => {
    let result: unknown;
    service.searchTags('sty').subscribe((r) => (result = r));

    const req = ctrl.expectOne((r) => r.url === '/tiny-model-manager/api/tags');
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('q')).toBe('sty');
    req.flush({ success: true, data: ['style', 'stylized'] });
    expect(result).toEqual(['style', 'stylized']);
  });
});
