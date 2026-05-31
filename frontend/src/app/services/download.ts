import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, interval, switchMap, startWith, shareReplay, from, of } from 'rxjs';
import { map, pairwise, mergeMap, catchError } from 'rxjs/operators';

export interface DownloadTask {
  id: string;
  url: string;
  model_type: string;
  filename: string;
  platform: string;
  source_id: string;
  status: 'queued' | 'downloading' | 'done' | 'error';
  progress: number;
  downloaded_bytes: number;
  total_bytes: number;
  error: string | null;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class DownloadService {
  readonly activeTasks$: Observable<DownloadTask[]>;
  readonly completedTasks$: Observable<DownloadTask>;

  constructor(private http: HttpClient) {
    this.activeTasks$ = interval(2000).pipe(
      startWith(0),
      switchMap(() =>
        this.http.get<{ success: boolean; data: DownloadTask[] }>(`${API}/download/status`).pipe(
          map((r) => r.data),
          catchError(() => of([] as DownloadTask[])),
        ),
      ),
      shareReplay(1),
    );

    this.completedTasks$ = this.activeTasks$.pipe(
      pairwise(),
      mergeMap(([prev, curr]) =>
        from(
          curr.filter(
            (task) =>
              (task.status === 'done' || task.status === 'error') &&
              prev.find((p) => p.id === task.id)?.status !== task.status,
          ),
        ),
      ),
    );
  }

  startDownload(
    url: string,
    model_type: string,
    filename: string,
    platform: string,
    source_id = '',
  ): Observable<{ task_id: string }> {
    return this.http
      .post<{
        success: boolean;
        data: { task_id: string };
      }>(`${API}/download`, { url, model_type, filename, platform, source_id })
      .pipe(map((r) => r.data));
  }
}
