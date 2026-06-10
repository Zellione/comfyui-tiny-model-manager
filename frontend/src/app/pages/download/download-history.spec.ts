import { TestBed } from '@angular/core/testing';
import { of, throwError, EMPTY, Subject } from 'rxjs';
import { vi } from 'vitest';
import { DownloadHistory } from './download-history';
import { DownloadService, DownloadTask, DownloadHistoryEntry } from '../../services/download';
import { NotificationService } from '../../services/notification';

const mockDownloadService = {
  activeTasks$: of([] as DownloadTask[]),
  completedTasks$: EMPTY,
  cancelDownload: vi.fn().mockReturnValue(of(void 0)),
  getHistory: vi.fn().mockReturnValue(of({ entries: [] as DownloadHistoryEntry[], total: 0 })),
  redownload: vi.fn().mockReturnValue(of({ task_id: 'task-new' })),
};

const mockNotifService = {
  show: vi.fn(),
};

const historyEntry = (id: number): DownloadHistoryEntry => ({
  id,
  model_name: `model_${id}.safetensors`,
  source: 'civitai',
  model_id: '',
  version_id: String(id),
  file_url: `https://civitai.com/${id}.safetensors`,
  dest_path: `model_${id}.safetensors`,
  model_type: 'checkpoints',
  status: 'done',
  created_at: '2024-01-01T00:00:00',
  updated_at: '2024-01-01T00:00:00',
});

async function configureTestBed() {
  await TestBed.configureTestingModule({
    imports: [DownloadHistory],
    providers: [
      { provide: DownloadService, useValue: mockDownloadService },
      { provide: NotificationService, useValue: mockNotifService },
    ],
  }).compileComponents();
}

async function createFixture() {
  const fixture = TestBed.createComponent(DownloadHistory);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('DownloadHistory component', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([] as DownloadTask[]);
    mockDownloadService.getHistory.mockReturnValue(
      of({ entries: [] as DownloadHistoryEntry[], total: 0 }),
    );
    mockDownloadService.redownload.mockReturnValue(of({ task_id: 'task-new' }));
    await configureTestBed();
  });

  it('loads the first history page on construction', async () => {
    const entries = [historyEntry(1), historyEntry(2)];
    mockDownloadService.getHistory.mockReturnValue(of({ entries, total: 2 }));
    const fixture = await createFixture();
    expect(mockDownloadService.getHistory).toHaveBeenCalled();
    expect(fixture.componentInstance.historyEntries()).toHaveLength(2);
  });

  it('historyHasMore is true when entries count is less than total', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyEntries.set([historyEntry(1), historyEntry(2)]);
    c.historyTotal.set(5);
    expect(c.historyHasMore()).toBe(true);
  });

  it('historyHasMore is false when entries count equals total', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyEntries.set([historyEntry(1)]);
    c.historyTotal.set(1);
    expect(c.historyHasMore()).toBe(false);
  });

  it('historyTaskMap maps tasks by history_id', async () => {
    const task: DownloadTask = {
      id: 'task-h1',
      url: 'https://civitai.com/m.safetensors',
      model_type: 'checkpoints',
      filename: 'm.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'downloading',
      progress: 50,
      downloaded_bytes: 512,
      total_bytes: 1024,
      error: null,
      history_id: 42,
    };
    mockDownloadService.activeTasks$ = of([task]);
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.historyTaskMap().get(42)?.id).toBe('task-h1');
  });

  it('historyTaskMap excludes tasks without history_id', async () => {
    const task: DownloadTask = {
      id: 'task-h2',
      url: 'https://civitai.com/m.safetensors',
      model_type: 'checkpoints',
      filename: 'm.safetensors',
      platform: 'civitai',
      source_id: '1',
      status: 'downloading',
      progress: 50,
      downloaded_bytes: 512,
      total_bytes: 1024,
      error: null,
      history_id: null,
    };
    mockDownloadService.activeTasks$ = of([task]);
    await configureTestBed();
    const fixture = await createFixture();
    expect(fixture.componentInstance.historyTaskMap().size).toBe(0);
  });

  it('loadHistory(true) resets entries and populates from service', async () => {
    const entries = [historyEntry(1), historyEntry(2)];
    mockDownloadService.getHistory.mockReturnValue(of({ entries, total: 2 }));
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.loadHistory(true);
    await fixture.whenStable();

    expect(c.historyEntries()).toHaveLength(2);
    expect(c.historyTotal()).toBe(2);
    expect(c.historyLoading()).toBe(false);
  });

  it('loadHistory(true) resets page to 1', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyPage.set(3);

    c.loadHistory(true);
    await fixture.whenStable();

    expect(c.historyPage()).toBe(1);
  });

  it('loadHistory(false) appends entries to existing list', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyEntries.set([historyEntry(1)]);
    mockDownloadService.getHistory.mockReturnValue(of({ entries: [historyEntry(2)], total: 2 }));

    c.loadHistory(false);
    await fixture.whenStable();

    expect(c.historyEntries()).toHaveLength(2);
  });

  it('loadHistory error sets historyLoadMoreError and clears loading', async () => {
    mockDownloadService.getHistory.mockReturnValue(throwError(() => new Error('Network error')));
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.loadHistory(true);
    await fixture.whenStable();

    expect(c.historyLoadMoreError()).toBe('Failed to load history');
    expect(c.historyLoading()).toBe(false);
  });

  it('historyLoadMore increments page and appends entries', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    c.historyPage.set(1);
    c.historyEntries.set([historyEntry(1)]);
    mockDownloadService.getHistory.mockReturnValue(of({ entries: [historyEntry(2)], total: 2 }));

    c.historyLoadMore();
    await fixture.whenStable();

    expect(c.historyPage()).toBe(2);
    expect(c.historyEntries()).toHaveLength(2);
  });

  it('redownload adds id to historyRedownloadingIds during request then removes on success', async () => {
    const subject = new Subject<{ task_id: string }>();
    mockDownloadService.redownload.mockReturnValue(subject.asObservable());
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    const entry = historyEntry(1);

    c.redownload(entry);
    expect(c.historyRedownloadingIds().has(1)).toBe(true);

    subject.next({ task_id: 'task-new' });
    subject.complete();
    expect(c.historyRedownloadingIds().has(1)).toBe(false);
  });

  it('redownload success emits switchToActive', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    let emitted = false;
    c.switchToActive.subscribe(() => (emitted = true));

    c.redownload(historyEntry(1));
    await fixture.whenStable();

    expect(emitted).toBe(true);
  });

  it('redownload success shows success notification', async () => {
    const fixture = await createFixture();
    const entry = historyEntry(1);

    fixture.componentInstance.redownload(entry);
    await fixture.whenStable();

    expect(mockNotifService.show).toHaveBeenCalledWith(
      'success',
      expect.stringContaining(entry.model_name),
    );
  });

  it('redownload error shows error notification', async () => {
    mockDownloadService.redownload.mockReturnValue(throwError(() => new Error('failed')));
    const fixture = await createFixture();
    const entry = historyEntry(1);

    fixture.componentInstance.redownload(entry);
    await fixture.whenStable();

    expect(mockNotifService.show).toHaveBeenCalledWith(
      'error',
      expect.stringContaining(entry.model_name),
    );
  });

  it('redownload error clears historyRedownloadingIds', async () => {
    mockDownloadService.redownload.mockReturnValue(throwError(() => new Error('failed')));
    const fixture = await createFixture();
    const entry = historyEntry(1);

    fixture.componentInstance.redownload(entry);
    await fixture.whenStable();

    expect(fixture.componentInstance.historyRedownloadingIds().has(1)).toBe(false);
  });

  it('onCancelTask tracks then clears the cancelling id', async () => {
    const subject = new Subject<void>();
    mockDownloadService.cancelDownload.mockReturnValue(subject.asObservable());
    const fixture = await createFixture();
    const c = fixture.componentInstance;

    c.onCancelTask('task-x');
    expect(c.cancellingIds().has('task-x')).toBe(true);

    subject.next();
    subject.complete();
    expect(c.cancellingIds().has('task-x')).toBe(false);
  });

  it('historyStatusLabel returns human-readable labels', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.historyStatusLabel('done')).toBe('Done');
    expect(c.historyStatusLabel('error')).toBe('Error');
    expect(c.historyStatusLabel('cancelled')).toBe('Cancelled');
    expect(c.historyStatusLabel('downloading')).toBe('Downloading');
    expect(c.historyStatusLabel('deleted')).toBe('Deleted');
  });

  it('historyStatusLabel returns raw status for unknown values', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.historyStatusLabel('unknown' as DownloadHistoryEntry['status'])).toBe('unknown');
  });

  it('canRedownload returns true for error, cancelled, and deleted', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.canRedownload('error')).toBe(true);
    expect(c.canRedownload('cancelled')).toBe(true);
    expect(c.canRedownload('deleted')).toBe(true);
  });

  it('canRedownload returns false for done and downloading', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.canRedownload('done')).toBe(false);
    expect(c.canRedownload('downloading')).toBe(false);
  });
});
