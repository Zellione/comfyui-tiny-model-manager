import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, interval, switchMap, startWith, shareReplay } from 'rxjs';
import { map } from 'rxjs/operators';

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

  constructor(private http: HttpClient) {
    this.activeTasks$ = interval(2000).pipe(
      startWith(0),
      switchMap(() =>
        this.http
          .get<{ success: boolean; data: DownloadTask[] }>(`${API}/download/status`)
          .pipe(map((r) => r.data)),
      ),
      shareReplay(1),
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
