import { TestBed } from '@angular/core/testing';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { TextDiffField, diffLines } from './text-diff-field';

async function createFixture(oldValue = '', newValue = '', lastEditedAt: string | null = null) {
  await TestBed.configureTestingModule({
    imports: [TextDiffField],
    providers: [provideTranslateServiceForTests()],
  }).compileComponents();
  const fixture = TestBed.createComponent(TextDiffField);
  fixture.componentRef.setInput('oldValue', oldValue);
  fixture.componentRef.setInput('newValue', newValue);
  fixture.componentRef.setInput('lastEditedAt', lastEditedAt);
  fixture.detectChanges();
  return fixture;
}

describe('diffLines()', () => {
  it('returns equal lines when strings are identical', () => {
    const result = diffLines('foo\nbar', 'foo\nbar');
    expect(result.every((l) => l.type === 'equal')).toBe(true);
  });

  it('marks added lines as add', () => {
    const result = diffLines('', 'new line');
    expect(result.some((l) => l.type === 'add' && l.text === 'new line')).toBe(true);
  });

  it('marks removed lines as remove', () => {
    const result = diffLines('old line', '');
    expect(result.some((l) => l.type === 'remove' && l.text === 'old line')).toBe(true);
  });

  it('handles mixed changes', () => {
    const result = diffLines('a\nb\nc', 'a\nd\nc');
    const types = result.map((l) => l.type);
    expect(types).toContain('equal');
    expect(types).toContain('add');
    expect(types).toContain('remove');
  });
});

describe('TextDiffField component', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('defaults to old when oldValue is non-empty', async () => {
    const fixture = await createFixture('existing text', 'new text');
    expect(fixture.componentInstance.selected()).toBe('old');
  });

  it('defaults to new when oldValue is empty', async () => {
    const fixture = await createFixture('', 'new text');
    expect(fixture.componentInstance.selected()).toBe('new');
  });

  it('defaults to new when oldValue is whitespace only', async () => {
    const fixture = await createFixture('   ', 'new text');
    expect(fixture.componentInstance.selected()).toBe('new');
  });

  it('shows edited icon when lastEditedAt is set', async () => {
    const fixture = await createFixture('old', 'new', '2024-01-01T00:00:00Z');
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.edited-icon')).not.toBeNull();
  });

  it('hides edited icon when lastEditedAt is null', async () => {
    const fixture = await createFixture('old', 'new', null);
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.edited-icon')).toBeNull();
  });

  it('selectOld() sets selected to old', async () => {
    const fixture = await createFixture('', 'new');
    fixture.componentInstance.selectOld();
    expect(fixture.componentInstance.selected()).toBe('old');
  });

  it('selectNew() sets selected to new', async () => {
    const fixture = await createFixture('existing', 'new');
    fixture.componentInstance.selectNew();
    expect(fixture.componentInstance.selected()).toBe('new');
  });
});
