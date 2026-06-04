import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { RefetchReviewModal } from './refetch-review-modal';
import { ModelService, RefetchPreviewResponse, RefetchResult } from '../../services/model';

const makePreviewData = (
  overrides: Partial<RefetchPreviewResponse> = {},
): RefetchPreviewResponse => ({
  old: {
    description: 'Old desc',
    trigger_words: ['old_tw'],
    tags: ['old_tag'],
    base_model: 'SDXL 1.0',
    media: [],
    last_edited_at: { description: null, trigger_words: null, tags: null, base_model: null },
  },
  new: {
    description: 'New desc',
    trigger_words: ['new_tw'],
    tags: ['new_tag'],
    base_model: 'Flux.1 D',
    media_urls: ['https://example.com/img.jpg'],
  },
  expires_at: new Date(Date.now() + 300_000).toISOString(),
  no_changes: false,
  ...overrides,
});

const mockModelService = {
  refetchApply: vi.fn(() => of({ removed: false, meta: {} } as RefetchResult)),
};

async function createFixture(data = makePreviewData()) {
  await TestBed.configureTestingModule({
    imports: [RefetchReviewModal],
    providers: [{ provide: ModelService, useValue: mockModelService }],
  }).compileComponents();
  const fixture = TestBed.createComponent(RefetchReviewModal);
  fixture.componentRef.setInput('data', data);
  fixture.componentRef.setInput('modelType', 'loras');
  fixture.componentRef.setInput('modelPath', 'test.safetensors');
  fixture.detectChanges();
  return fixture;
}

describe('RefetchReviewModal', () => {
  afterEach(() => {
    vi.clearAllMocks();
    TestBed.resetTestingModule();
  });

  it('initialises with descriptionChoice old when oldValue is non-empty', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.descriptionChoice()).toBe('old');
  });

  it('initialises with descriptionChoice new when old description is empty', async () => {
    const data = makePreviewData();
    data.old.description = '';
    const fixture = await createFixture(data);
    expect(fixture.componentInstance.descriptionChoice()).toBe('new');
  });

  it('buildApplyRequest uses old description when choice is old', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.descriptionChoice.set('old');
    cmp.applySelected();
    expect(mockModelService.refetchApply).toHaveBeenCalledWith(
      'loras',
      'test.safetensors',
      expect.objectContaining({ description: 'Old desc' }),
    );
  });

  it('buildApplyRequest uses new description when choice is new', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.descriptionChoice.set('new');
    cmp.applySelected();
    expect(mockModelService.refetchApply).toHaveBeenCalledWith(
      'loras',
      'test.safetensors',
      expect.objectContaining({ description: 'New desc' }),
    );
  });

  it('buildApplyRequest sets media_urls to empty when replace_media is false', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.replaceImages.set(false);
    cmp.applySelected();
    expect(mockModelService.refetchApply).toHaveBeenCalledWith(
      'loras',
      'test.safetensors',
      expect.objectContaining({ replace_media: false, media_urls: [] }),
    );
  });

  it('Apply button is disabled when expired', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.expired.set(true);
    fixture.detectChanges();
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('button.btn.primary');
    expect(btn?.disabled).toBe(true);
  });

  it('countdown is shown when secondsRemaining < 120', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.secondsRemaining.set(60);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.countdown')).not.toBeNull();
  });

  it('countdown is hidden when secondsRemaining is null', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.secondsRemaining.set(null);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.countdown')).toBeNull();
  });

  it('cancelled output emits when ESC is pressed', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    let count = 0;
    cmp.cancelled.subscribe(() => count++);
    cmp.onEscapeKey();
    expect(count).toBe(1);
  });
});
