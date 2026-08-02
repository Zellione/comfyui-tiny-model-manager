import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
// The extension module lives outside src/ because ComfyUI loads it directly from web/.
import { NODE_TYPE_MAP } from '../../../../js/workflow-insert.js';
import { WorkflowService, WORKFLOW_INSERTABLE_TYPES, isWorkflowInsertable } from './workflow';

describe('WorkflowService', () => {
  let service: WorkflowService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), WorkflowService],
    });
    service = TestBed.inject(WorkflowService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('addToWorkflow POSTs model_type and filename to /workflow/insert', () => {
    service.addToWorkflow('loras', 'my_lora.safetensors').subscribe();
    const req = http.expectOne('/tiny-model-manager/api/workflow/insert');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ model_type: 'loras', filename: 'my_lora.safetensors' });
  });
});

describe('WORKFLOW_INSERTABLE_TYPES', () => {
  // Guards against drift: the frontend cannot import the extension module at runtime, so a
  // type added on one side must be added on the other or queued items are never inserted.
  it('matches NODE_TYPE_MAP in js/workflow-insert.js', () => {
    expect([...WORKFLOW_INSERTABLE_TYPES].sort()).toEqual(Object.keys(NODE_TYPE_MAP).sort());
  });

  it('reports whether a model type can be inserted', () => {
    expect(isWorkflowInsertable('loras')).toBe(true);
    expect(isWorkflowInsertable('clip')).toBe(false);
    expect(isWorkflowInsertable('')).toBe(false);
  });
});
