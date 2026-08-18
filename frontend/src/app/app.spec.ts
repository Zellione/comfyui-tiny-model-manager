import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateServiceForTests } from '../test-helpers/translate-testing';
import { EMPTY, Subject } from 'rxjs';
import { vi } from 'vitest';
import { App } from './app';
import { DownloadService, DownloadTask } from './services/download';
import { NotificationService, Toast } from './services/notification';
import { BackendNotificationService } from './services/backend-notification';
import { signal } from '@angular/core';

const mockDownloadService = { completedTasks$: EMPTY, activeTasks$: EMPTY };

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        { provide: DownloadService, useValue: mockDownloadService },
        provideTranslateServiceForTests(),
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should start in dark mode', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance.isDark()).toBe(true);
  });

  it('should toggle theme from dark to light', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    app.toggleTheme();
    expect(app.isDark()).toBe(false);
  });

  it('should toggle theme back to dark', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    app.toggleTheme(); // dark → light
    app.toggleTheme(); // light → dark
    expect(app.isDark()).toBe(true);
  });

  it('should render a theme toggle button', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const btn = (fixture.nativeElement as HTMLElement).querySelector('.icon-btn');
    expect(btn).toBeTruthy();
  });
});

describe('App — download failure notifications', () => {
  const completed$ = new Subject<DownloadTask>();
  // The Toast component in App's template reads `toasts` as a signal, so the mock
  // must provide it alongside the spied `show`.
  const mockNotifService = { show: vi.fn(), toasts: signal<Toast[]>([]), dismiss: vi.fn() };

  const failedTask = (extra: Partial<DownloadTask>): DownloadTask =>
    ({
      id: 't1',
      url: 'https://civitai.com/api/download/models/1',
      model_type: 'checkpoints',
      filename: 'model.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'error',
      progress: 0,
      downloaded_bytes: 0,
      total_bytes: 0,
      error: 'boom',
      history_id: null,
      ...extra,
    }) as DownloadTask;

  beforeEach(async () => {
    vi.clearAllMocks();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        {
          provide: DownloadService,
          useValue: { completedTasks$: completed$, activeTasks$: EMPTY },
        },
        { provide: NotificationService, useValue: mockNotifService },
        { provide: BackendNotificationService, useValue: { start: vi.fn() } },
        provideTranslateServiceForTests(),
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
  });

  it('shows the paid-model hint when error_code is early_access', () => {
    completed$.next(failedTask({ error_code: 'early_access' }));
    expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.stringContaining('Buzz'));
  });

  it('shows the API-key hint when error_code is login_required', () => {
    completed$.next(failedTask({ error_code: 'login_required' }));
    expect(mockNotifService.show).toHaveBeenCalledWith('error', expect.stringContaining('API key'));
  });

  it('falls back to the raw error message for unknown error codes', () => {
    completed$.next(failedTask({ error: 'connection reset', error_code: '' }));
    expect(mockNotifService.show).toHaveBeenCalledWith(
      'error',
      expect.stringContaining('connection reset'),
    );
  });
});
