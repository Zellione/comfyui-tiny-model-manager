import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class TagService {
  private readonly http = inject(HttpClient);

  searchTags(q: string): Observable<string[]> {
    return this.http
      .get<{ success: boolean; data: string[] }>(`${API}/tags`, { params: { q } })
      .pipe(map((r) => r.data));
  }
}
