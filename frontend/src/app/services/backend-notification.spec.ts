import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import { BackendNotificationService } from './backend-notification';
import { NotificationService } from './notification';

const URL = '/tiny-model-manager/api/notifications';

describe('BackendNotificationService', () => {
  let service: BackendNotificationService;
  let ctrl: HttpTestingController;
  const mockNotif = { show: vi.fn() };

  beforeEach(() => {
    vi.useFakeTimers();
    mockNotif.show.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        BackendNotificationService,
        { provide: NotificationService, useValue: mockNotif },
      ],
    });
    service = TestBed.inject(BackendNotificationService);
    ctrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('shows every flushed backend notification on each poll tick', () => {
    service.start();
    vi.advanceTimersByTime(10_000);

    ctrl.expectOne(URL).flush({
      success: true,
      data: [
        { id: 'a', type: 'success', message: 'downloaded' },
        { id: 'b', type: 'error', message: 'failed' },
      ],
    });

    expect(mockNotif.show).toHaveBeenCalledWith('success', 'downloaded');
    expect(mockNotif.show).toHaveBeenCalledWith('error', 'failed');
  });

  it('keeps polling after an HTTP error', () => {
    service.start();
    vi.advanceTimersByTime(10_000);
    ctrl.expectOne(URL).error(new ProgressEvent('network down'));

    vi.advanceTimersByTime(10_000);
    ctrl
      .expectOne(URL)
      .flush({ success: true, data: [{ id: 'c', type: 'success', message: 'recovered' }] });

    expect(mockNotif.show).toHaveBeenCalledWith('success', 'recovered');
  });

  it('ignores unsuccessful responses', () => {
    service.start();
    vi.advanceTimersByTime(10_000);
    ctrl.expectOne(URL).flush({ success: false, data: [] });

    expect(mockNotif.show).not.toHaveBeenCalled();
  });
});
