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
    return this.http.get<{ success: boolean; data: Record<string, ModelFile[]> }>(`${API}/models`).pipe(
      map(r => r.data)
    );
  }

  deleteModel(modelType: string, path: string): Observable<void> {
    return this.http.delete<void>(`${API}/models/${modelType}/${path}`);
  }

  getMetadata(modelType: string, path: string): Observable<ModelMeta> {
    return this.http
      .get<{ success: boolean; data: ModelMeta }>(`${API}/models/${modelType}/${path}/metadata`)
      .pipe(map(r => r.data));
  }

  updateMetadata(modelType: string, path: string, meta: Partial<ModelMeta>): Observable<void> {
    return this.http.put<void>(`${API}/models/${modelType}/${path}/metadata`, meta);
  }

  refetchMetadata(modelType: string, path: string): Observable<ModelMeta> {
    return this.http
      .post<{ success: boolean; data: ModelMeta }>(`${API}/models/${modelType}/${path}/refetch`, {})
      .pipe(map(r => r.data));
  }
}
