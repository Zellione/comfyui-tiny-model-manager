import { TestBed } from '@angular/core/testing';
import { of, throwError, EMPTY, Subject } from 'rxjs';
import { vi } from 'vitest';
import { HttpErrorResponse } from '@angular/common/http';
import { DownloadQueue } from './download-queue';
import { DownloadService, DownloadTask } from '../../services/download';

const mockDownloadService = {
  activeTasks$: of([] as DownloadTask[]),
  completedTasks$: EMPTY,
  cancelDownload: vi.fn().mockReturnValue(of(void 0)),
};

const activeTask = (): DownloadTask => ({
  id: 'task-1',
  url: 'https://civitai.com/m.safetensors',
  model_type: 'loras',
  filename: 'm.safetensors',
  platform: 'civitai',
  source_id: '123',
  status: 'downloading',
  progress: 50,
  downloaded_bytes: 512,
  total_bytes: 1024,
  error: null,
  history_id: null,
});

async function configureTestBed() {
  await TestBed.configureTestingModule({
    imports: [DownloadQueue],
    providers: [{ provide: DownloadService, useValue: mockDownloadService }],
  }).compileComponents();
}

async function createFixture() {
  const fixture = TestBed.createComponent(DownloadQueue);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('DownloadQueue component', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDownloadService.activeTasks$ = of([activeTask()]);
    mockDownloadService.cancelDownload.mockReturnValue(of(void 0));
    await configureTestBed();
  });

  it('onCancelTask calls cancelDownload with the task id', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.onCancelTask('task-1');
    expect(mockDownloadService.cancelDownload).toHaveBeenCalledWith('task-1');
  });

  it('adds task to cancelledIds on success', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.onCancelTask('task-1');
    expect(fixture.componentInstance.cancelledIds().has('task-1')).toBe(true);
  });

  it('adds task to cancelledIds on 404 (already done)', async () => {
    mockDownloadService.cancelDownload.mockReturnValue(
      throwError(() => new HttpErrorResponse({ status: 404 })),
    );
    const fixture = await createFixture();
    fixture.componentInstance.onCancelTask('task-1');
    expect(fixture.componentInstance.cancelledIds().has('task-1')).toBe(true);
  });

  it('tracks in-flight cancellation in cancellingIds', async () => {
    const subject = new Subject<void>();
    mockDownloadService.cancelDownload.mockReturnValue(subject.asObservable());
    const fixture = await createFixture();

    fixture.componentInstance.onCancelTask('task-1');
    expect(fixture.componentInstance.cancellingIds().has('task-1')).toBe(true);

    subject.next();
    subject.complete();
    expect(fixture.componentInstance.cancellingIds().has('task-1')).toBe(false);
  });

  it('displayTasks excludes cancelled ids', async () => {
    const fixture = await createFixture();
    const c = fixture.componentInstance;
    expect(c.displayTasks().length).toBe(1);
    c.onCancelTask('task-1');
    expect(c.displayTasks().length).toBe(0);
  });

  it('onCancelAll cancels every display task', async () => {
    const tasks: DownloadTask[] = [
      { ...activeTask(), id: 'task-1', filename: 'a.safetensors' },
      { ...activeTask(), id: 'task-2', filename: 'b.safetensors', status: 'queued' },
    ];
    mockDownloadService.activeTasks$ = of(tasks);
    const fixture = await createFixture();
    fixture.componentInstance.onCancelAll();
    expect(mockDownloadService.cancelDownload).toHaveBeenCalledWith('task-1');
    expect(mockDownloadService.cancelDownload).toHaveBeenCalledWith('task-2');
  });

  it('hasCancellableTasks is false when all tasks are done', async () => {
    mockDownloadService.activeTasks$ = of([{ ...activeTask(), status: 'done' }]);
    const fixture = await createFixture();
    expect(fixture.componentInstance.hasCancellableTasks()).toBe(false);
  });

  it('hasCancellableTasks is true when at least one task is downloading', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.hasCancellableTasks()).toBe(true);
  });

  it('hasCancellableTasks is false when all tasks are errors', async () => {
    mockDownloadService.activeTasks$ = of([{ ...activeTask(), status: 'error' }]);
    const fixture = await createFixture();
    expect(fixture.componentInstance.hasCancellableTasks()).toBe(false);
  });

  it('activePct formats the progress as a percentage string', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.activePct({ ...activeTask(), progress: 42.7 })).toBe('43%');
  });
});
