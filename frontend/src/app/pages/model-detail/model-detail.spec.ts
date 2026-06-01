import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ModelDetail } from './model-detail';
import { ModelService } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';

const makeMeta = (overrides = {}) => ({
  description: 'A test model',
  trigger_words: ['foo', 'bar'],
  tags: ['portrait'],
  media: [],
  base_model: 'SDXL 1.0',
  source_platform: 'civitai',
  source_url: 'https://civitai.com/models/1',
  size_bytes: 1073741824, // 1 GB
  ...overrides,
});

const mockModelService = {
  getMetadata: vi.fn(() => of(makeMeta())),
  updateMetadata: vi.fn(() => of(undefined)),
  refetchMetadata: vi.fn(() => of(makeMeta())),
  deleteModel: vi.fn(() => of(undefined)),
  getModelTypes: vi.fn(() => of(['checkpoints', 'loras'])),
  moveModel: vi.fn(() => of(undefined)),
};

const mockWorkflowService = { addToWorkflow: vi.fn(() => of(undefined)) };
const mockNotifService = { show: vi.fn() };

describe('ModelDetail', () => {
  let component: ModelDetail;

  beforeEach(async () => {
    vi.clearAllMocks();
    await TestBed.configureTestingModule({
      imports: [ModelDetail],
      providers: [
        provideRouter([{ path: 'models', children: [] }]),
        { provide: ModelService, useValue: mockModelService },
        { provide: WorkflowService, useValue: mockWorkflowService },
        { provide: NotificationService, useValue: mockNotifService },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(ModelDetail);
    component = fixture.componentInstance;
    component.modelType = 'loras';
    component.modelPath = 'my-lora.safetensors';
    component.editType = 'loras';
    component.meta.set(makeMeta());
    component.loading.set(false);
  });

  describe('enterEdit / cancelEdit', () => {
    it('enterEdit() sets editMode to true', () => {
      component.enterEdit();
      expect(component.editMode()).toBe(true);
    });

    it('cancelEdit() sets editMode to false', () => {
      component.enterEdit();
      component.cancelEdit();
      expect(component.editMode()).toBe(false);
    });

    it('cancelEdit() resets editMeta to current meta values', () => {
      component.editMeta = { description: 'changed', trigger_words: ['new'] };
      component.cancelEdit();
      expect(component.editMeta.description).toBe('A test model');
      expect(component.editMeta.trigger_words).toEqual(['foo', 'bar']);
    });
  });

  describe('uninstall', () => {
    it('calls deleteModel with modelType and modelPath', () => {
      component.uninstall();
      expect(mockModelService.deleteModel).toHaveBeenCalledWith('loras', 'my-lora.safetensors');
    });

    it('shows success notification on successful delete', () => {
      component.uninstall();
      expect(mockNotifService.show).toHaveBeenCalledWith(
        'success',
        expect.stringContaining('uninstalled'),
      );
    });

    it('shows notification and dismisses banner on error', () => {
      mockModelService.deleteModel.mockReturnValueOnce(throwError(() => new Error('disk full')));
      component.showUninstallConfirm.set(true);
      component.uninstall();
      expect(mockNotifService.show).toHaveBeenCalledWith('error', 'disk full');
      expect(component.showUninstallConfirm()).toBe(false);
      expect(component.deleting()).toBe(false);
    });
  });

  describe('formatBytes', () => {
    it('returns empty string for 0', () => {
      expect(component.formatBytes(0)).toBe('');
    });

    it('formats bytes', () => {
      expect(component.formatBytes(512)).toBe('512.0 B');
    });

    it('formats megabytes', () => {
      expect(component.formatBytes(57400000)).toMatch(/MB/);
    });

    it('formats gigabytes', () => {
      expect(component.formatBytes(1073741824)).toBe('1.0 GB');
    });
  });

  describe('eyebrowParts', () => {
    it('includes modelType, base_model, and formatted size', () => {
      const parts = component.eyebrowParts();
      expect(parts).toContain('loras');
      expect(parts).toContain('SDXL 1.0');
      expect(parts.some((p) => p.includes('GB'))).toBe(true);
    });

    it('omits empty base_model', () => {
      component.meta.set(makeMeta({ base_model: '', size_bytes: 0 }));
      const parts = component.eyebrowParts();
      expect(parts).toEqual(['loras']);
    });
  });

  describe('sourceName', () => {
    it('returns CivitAI for civitai platform', () => {
      expect(component.sourceName()).toBe('CivitAI');
    });

    it('returns HuggingFace for huggingface platform', () => {
      component.meta.set(makeMeta({ source_platform: 'huggingface' }));
      expect(component.sourceName()).toBe('HuggingFace');
    });

    it('returns source for unknown platform', () => {
      component.meta.set(makeMeta({ source_platform: '' }));
      expect(component.sourceName()).toBe('source');
    });
  });

  describe('save exits edit mode', () => {
    it('exits editMode on successful save without type change', () => {
      component.enterEdit();
      component.save();
      expect(component.editMode()).toBe(false);
    });
  });
});
