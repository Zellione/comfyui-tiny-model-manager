import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

const API = '/tiny-model-manager/api';

/** The settings envelope returned by `GET /api/settings` (secrets arrive masked as `***`). */
export interface TmmSettings {
  civitai_api_key: string;
  hf_token: string;
  media_dir: string;
  media_dir_default: string;
  organize_into_subfolders: boolean;
  cleanup_stale_media_on_start: boolean;
  missing_models_integration: boolean;
}

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly http = inject(HttpClient);

  getSettings(): Observable<TmmSettings> {
    return this.http
      .get<{ success: boolean; data: TmmSettings }>(`${API}/settings`)
      .pipe(map((r) => r.data));
  }

  updateSettings(patch: Partial<TmmSettings>): Observable<void> {
    return this.http.put<{ success: boolean }>(`${API}/settings`, patch).pipe(map(() => undefined));
  }

  getOrganizeEnabled(): Observable<boolean> {
    return this.getSettings().pipe(map((s) => s.organize_into_subfolders ?? false));
  }
}
