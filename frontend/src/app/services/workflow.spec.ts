import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { WorkflowService } from './workflow';

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
