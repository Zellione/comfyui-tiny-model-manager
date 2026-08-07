import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { SettingsService } from './settings';

describe('SettingsService', () => {
  let service: SettingsService;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), SettingsService],
    });
    service = TestBed.inject(SettingsService);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => ctrl.verify());

  it('getOrganizeEnabled unwraps the flag', () => {
    let result: boolean | undefined;
    service.getOrganizeEnabled().subscribe((r) => (result = r));

    const req = ctrl.expectOne('/tiny-model-manager/api/settings');
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: { organize_into_subfolders: true } });
    expect(result).toBe(true);
  });

  it('getOrganizeEnabled defaults a missing flag to false', () => {
    let result: boolean | undefined;
    service.getOrganizeEnabled().subscribe((r) => (result = r));

    ctrl.expectOne('/tiny-model-manager/api/settings').flush({ success: true, data: {} });
    expect(result).toBe(false);
  });

  it('getSettings unwraps the whole envelope', () => {
    let result: { missing_models_integration?: boolean } | undefined;
    service.getSettings().subscribe((r) => (result = r));

    ctrl
      .expectOne('/tiny-model-manager/api/settings')
      .flush({ success: true, data: { missing_models_integration: false } });
    expect(result?.missing_models_integration).toBe(false);
  });

  it('updateSettings PUTs the patch', () => {
    let completed = false;
    service.updateSettings({ missing_models_integration: true }).subscribe(() => {
      completed = true;
    });

    const req = ctrl.expectOne('/tiny-model-manager/api/settings');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ missing_models_integration: true });
    req.flush({ success: true });
    expect(completed).toBe(true);
  });
});
