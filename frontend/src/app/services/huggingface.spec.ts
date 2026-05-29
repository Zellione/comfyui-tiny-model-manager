import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HuggingFaceService } from './huggingface';

describe('HuggingFaceService', () => {
  let service: HuggingFaceService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), HuggingFaceService],
    });
    service = TestBed.inject(HuggingFaceService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('search GETs HuggingFace search endpoint and unwraps data', () => {
    const mockData = {
      items: [{ id: 'user/repo', modelId: 'user/repo', downloads: 100, tags: [] }],
      hasMore: false,
      nextPage: 1,
    };
    let result: unknown;
    service.search('lora').subscribe((r) => (result = r));
    const req = http.expectOne((r) => r.url.includes('/api/search/huggingface'));
    req.flush({ success: true, data: mockData });
    expect(result).toEqual(mockData);
  });

  it('getFiles GETs files endpoint', () => {
    service.getFiles('user/repo').subscribe();
    const req = http.expectOne((r) => r.url.includes('/api/search/huggingface/files'));
    expect(req.request.params.get('repo')).toBe('user/repo');
    req.flush({ success: true, data: [] });
  });

  it('getReadme GETs readme endpoint and unwraps description', () => {
    let result: unknown;
    service.getReadme('user/repo').subscribe((r) => (result = r));
    const req = http.expectOne((r) => r.url.includes('/api/huggingface/readme'));
    req.flush({ success: true, data: { description: '# README\n\nHello' } });
    expect(result).toBe('# README\n\nHello');
  });

  it('resolveDirectLink GETs resolve endpoint and unwraps data', () => {
    let result: unknown;
    service.resolveDirectLink('user/repo').subscribe((r) => (result = r));
    const req = http.expectOne((r) => r.url.includes('/api/huggingface/resolve'));
    req.flush({ success: true, data: { image_urls: ['https://example.com/img.jpg'] } });
    expect(result).toEqual({ image_urls: ['https://example.com/img.jpg'] });
  });
});
