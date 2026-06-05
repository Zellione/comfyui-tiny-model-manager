import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly http = inject(HttpClient);

  getOrganizeEnabled(): Observable<boolean> {
    return this.http
      .get<{ success: boolean; data: { organize_into_subfolders: boolean } }>(`${API}/settings`)
      .pipe(map((r) => r.data.organize_into_subfolders ?? false));
  }
}
