import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';

const API = '/tiny-model-manager/api';

// Model types the ComfyUI extension can turn into a loader node.
//
// Must stay in sync with NODE_TYPE_MAP in js/workflow-insert.js: a queued item whose type is
// missing there is skipped by the extension and therefore never acked, so it lingers in the
// backend's pending list forever and leaves the card stuck under the "processing" overlay.
// `workflow.spec.ts` asserts both lists match, so drift fails the test suite.
export const WORKFLOW_INSERTABLE_TYPES = [
  'checkpoints',
  'loras',
  'vae',
  'controlnet',
  'embeddings',
  'upscale_models',
];

export function isWorkflowInsertable(modelType: string): boolean {
  return WORKFLOW_INSERTABLE_TYPES.includes(modelType);
}

@Injectable({ providedIn: 'root' })
export class WorkflowService {
  constructor(private readonly http: HttpClient) {}

  addToWorkflow(modelType: string, filename: string) {
    return this.http.post(`${API}/workflow/insert`, { model_type: modelType, filename });
  }
}
