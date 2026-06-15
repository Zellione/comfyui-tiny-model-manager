import { TestBed } from '@angular/core/testing';
import { of, EMPTY } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { TagService } from '../../services/tags';
import { TagAutocompleteInput } from './tag-autocomplete-input';

const mockTagService = {
  searchTags: vi.fn().mockReturnValue(EMPTY),
};

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [TagAutocompleteInput],
    providers: [
      { provide: TagService, useValue: mockTagService },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
  const fixture = TestBed.createComponent(TagAutocompleteInput);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('TagAutocompleteInput', () => {
  afterEach(() => {
    vi.clearAllMocks();
    TestBed.resetTestingModule();
  });

  it('creates successfully', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('panel is closed initially', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.open()).toBe(false);
  });

  it('onInput opens panel when value is non-empty', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('an');
    expect(cmp.open()).toBe(true);
  });

  it('onInput closes panel when value is empty', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('an');
    cmp.onInput('');
    expect(cmp.open()).toBe(false);
  });

  it('select emits tagAdded and clears the input', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    const emitted: string[] = [];
    cmp.tagAdded.subscribe((t) => emitted.push(t));
    cmp.onInput('an');
    cmp.select('anime');
    expect(emitted).toEqual(['anime']);
    expect(cmp.inputValue()).toBe('');
    expect(cmp.open()).toBe(false);
  });

  it('onEnter selects trimmed inputValue', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    const emitted: string[] = [];
    cmp.tagAdded.subscribe((t) => emitted.push(t));
    cmp.onInput('lora');
    cmp.onEnter();
    expect(emitted).toEqual(['lora']);
  });

  it('onEnter does nothing when input is blank', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    const emitted: string[] = [];
    cmp.tagAdded.subscribe((t) => emitted.push(t));
    cmp.onEnter();
    expect(emitted).toHaveLength(0);
  });

  it('suggestions from searchResultTags filtered by query, excluding selected', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    fixture.componentRef.setInput('searchResultTags', ['anime', 'action', 'lora']);
    fixture.componentRef.setInput('selectedTags', ['anime']);
    cmp.onInput('a');
    fixture.detectChanges();
    const suggestions = cmp.suggestions();
    expect(suggestions).toContain('action');
    expect(suggestions).not.toContain('anime');
  });

  it('db suggestions merged after search-result tags, capped at 5', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    fixture.componentRef.setInput('searchResultTags', ['alpha', 'alpha2']);
    mockTagService.searchTags.mockReturnValue(of(['alpha3', 'alpha4', 'alpha5', 'alpha6']));
    cmp.onInput('alpha');
    fixture.detectChanges();
    await fixture.whenStable();
    expect(cmp.suggestions().length).toBeLessThanOrEqual(5);
  });

  it('onDocClick keeps the panel open when the click target is inside the host', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('a');
    expect(cmp.open()).toBe(true);
    const inner = fixture.nativeElement.querySelector('input') as Node;
    cmp.onDocClick({ target: inner } as unknown as MouseEvent);
    expect(cmp.open()).toBe(true);
  });

  it('onDocClick closes the panel when the click target is outside the host', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('a');
    expect(cmp.open()).toBe(true);
    const outside = document.createElement('div');
    cmp.onDocClick({ target: outside } as unknown as MouseEvent);
    expect(cmp.open()).toBe(false);
  });

  it('onDocClick closes the panel when the click target is not a Node', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('a');
    expect(cmp.open()).toBe(true);
    cmp.onDocClick({ target: null } as unknown as MouseEvent);
    expect(cmp.open()).toBe(false);
  });

  it('escape closes the panel', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('a');
    expect(cmp.open()).toBe(true);
    cmp.onEscape();
    expect(cmp.open()).toBe(false);
  });
});
