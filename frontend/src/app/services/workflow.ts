import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class WorkflowService {
  constructor(private http: HttpClient) {}

  addToWorkflow(modelType: string, filename: string) {
    return this.http.post(`${API}/workflow/insert`, { model_type: modelType, filename });
  }
}
