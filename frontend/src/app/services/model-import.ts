import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

/**
 * Importing models from another ComfyUI installation's models folder (F-154).
 *
 * Both phases are backend jobs: a scan hashes the foreign folder against the local
 * library, an import copies the selected files in. The caller polls; this service only
 * starts jobs and reads their state.
 */

/** One model file found in the foreign folder. */
export interface ImportSourceFile {
  model_type: string;
  filename: string;
  size_bytes: number;
  /** pending | new | installed | unreadable */
  status: string;
  file_hash: string;
}

/** A file the user picked for import. */
export interface ImportSelection {
  model_type: string;
  filename: string;
  file_hash: string;
}

export interface ImportJobState {
  id: string;
  kind: string;
  source_root: string;
  /** running | done | error | cancelled */
  state: string;
  progress: number;
  error: string;
  files: ImportSourceFile[];
  imported: string[];
  skipped: string[];
  failed: { filename: string; reason: string }[];
}

export interface ScanStartResult {
  job_id: string;
  source_root: string;
}

const API = '/tiny-model-manager/api/import';

@Injectable({ providedIn: 'root' })
export class ModelImportService {
  private readonly http = inject(HttpClient);

  startScan(path: string): Observable<ScanStartResult> {
    return this.http
      .post<{ data: ScanStartResult }>(`${API}/scan`, { path })
      .pipe(map((r) => r.data));
  }

  pollScan(jobId: string): Observable<ImportJobState> {
    return this.http.get<{ data: ImportJobState }>(`${API}/scan/${jobId}`).pipe(map((r) => r.data));
  }

  startImport(sourceRoot: string, files: ImportSelection[]): Observable<{ job_id: string }> {
    return this.http
      .post<{ data: { job_id: string } }>(`${API}/start`, { source_root: sourceRoot, files })
      .pipe(map((r) => r.data));
  }

  pollJob(jobId: string): Observable<ImportJobState> {
    return this.http.get<{ data: ImportJobState }>(`${API}/jobs/${jobId}`).pipe(map((r) => r.data));
  }

  cancelJob(jobId: string): Observable<{ cancelled: boolean }> {
    return this.http
      .post<{ data: { cancelled: boolean } }>(`${API}/jobs/${jobId}/cancel`, {})
      .pipe(map((r) => r.data));
  }
}
