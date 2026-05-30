import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface ModelFile {
  filename: string;
  base_dir: string;
  size_bytes: number;
  modified_at: number;
  metadata?: ModelMeta;
}

export interface ModelMeta {
  description: string;
  trigger_words: string[];
  tags: string[];
  media: MediaItem[];
  base_model: string;
  source_platform: string;
  source_url: string;
  created_at?: string;
}

export interface MediaItem {
  id: number;
  media_type: string;
  local_path: string;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class ModelService {
  constructor(private http: HttpClient) {}

  listModels(): Observable<Record<string, ModelFile[]>> {
    return this.http
      .get<{ success: boolean; data: Record<string, ModelFile[]> }>(`${API}/models`)
      .pipe(map((r) => r.data));
  }

  deleteModel(modelType: string, path: string): Observable<void> {
    return this.http.delete<void>(`${API}/models/${modelType}/${path}`);
  }

  getMetadata(modelType: string, path: string): Observable<ModelMeta> {
    return this.http
      .get<{ success: boolean; data: ModelMeta }>(`${API}/models/${modelType}/${path}/metadata`)
      .pipe(map((r) => r.data));
  }

  updateMetadata(modelType: string, path: string, meta: Partial<ModelMeta>): Observable<void> {
    return this.http.put<void>(`${API}/models/${modelType}/${path}/metadata`, meta);
  }

  refetchMetadata(modelType: string, path: string): Observable<ModelMeta> {
    return this.http
      .post<{ success: boolean; data: ModelMeta }>(`${API}/models/${modelType}/${path}/refetch`, {})
      .pipe(map((r) => r.data));
  }

  getModelTypes(): Observable<string[]> {
    return this.http
      .get<{ success: boolean; data: string[] }>(`${API}/model-types`)
      .pipe(map((r) => r.data));
  }

  moveModel(modelType: string, path: string, newType: string): Observable<void> {
    return this.http.post<void>(`${API}/models/${modelType}/${path}/move`, { new_type: newType });
  }

  organizeIntoSubfolders(): Observable<{ moved: number; skipped: number; errors: number }> {
    return this.http
      .post<{
        success: boolean;
        data: { moved: number; skipped: number; errors: number };
      }>(`${API}/models/organize`, {})
      .pipe(map((r) => r.data));
  }
}
