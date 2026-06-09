import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { FilenameKeyword } from '../utils/filename-detector';

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class KeywordsService {
  private readonly http = inject(HttpClient);

  getKeywords(): Observable<FilenameKeyword[]> {
    return this.http
      .get<{ success: boolean; data: FilenameKeyword[] }>(`${API}/filename-keywords`)
      .pipe(map((r) => r.data));
  }

  createKeyword(
    keyword: string,
    base_model: string | null,
    model_type: string | null,
  ): Observable<{ id: number }> {
    return this.http
      .post<{ success: boolean; data: { id: number } }>(`${API}/filename-keywords`, {
        keyword,
        base_model,
        model_type,
      })
      .pipe(map((r) => r.data));
  }

  updateKeyword(
    id: number,
    keyword: string,
    base_model: string | null,
    model_type: string | null,
  ): Observable<void> {
    return this.http
      .put<void>(`${API}/filename-keywords/${id}`, { keyword, base_model, model_type })
      .pipe(map(() => undefined));
  }

  deleteKeyword(id: number): Observable<void> {
    return this.http.delete<void>(`${API}/filename-keywords/${id}`).pipe(map(() => undefined));
  }
}
