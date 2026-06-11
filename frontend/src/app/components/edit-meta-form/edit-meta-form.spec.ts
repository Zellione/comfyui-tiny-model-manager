import { TestBed } from '@angular/core/testing';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { vi } from 'vitest';
import { EditMetaForm } from './edit-meta-form';

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [EditMetaForm],
    providers: [provideTranslateServiceForTests()],
  }).compileComponents();
  const fixture = TestBed.createComponent(EditMetaForm);
  fixture.detectChanges();
  return fixture;
}

describe('EditMetaForm component', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('creates successfully', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance).toBeTruthy();
  });

  describe('trigger words', () => {
    it('addTriggerWord emits updated array and clears input', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      fixture.componentRef.setInput('triggerWords', ['existing']);
      const emitted: string[][] = [];
      cmp.triggerWordsChange.subscribe((v) => emitted.push(v));

      cmp.newTriggerWord = '  new word  ';
      cmp.addTriggerWord();

      expect(emitted).toEqual([['existing', 'new word']]);
      expect(cmp.newTriggerWord).toBe('');
    });

    it('addTriggerWord ignores blank input', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      const emitted: string[][] = [];
      cmp.triggerWordsChange.subscribe((v) => emitted.push(v));

      cmp.newTriggerWord = '   ';
      cmp.addTriggerWord();

      expect(emitted).toEqual([]);
    });

    it('removeTriggerWord emits filtered array', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      fixture.componentRef.setInput('triggerWords', ['foo', 'bar', 'baz']);
      const emitted: string[][] = [];
      cmp.triggerWordsChange.subscribe((v) => emitted.push(v));

      cmp.removeTriggerWord('bar');

      expect(emitted).toEqual([['foo', 'baz']]);
    });
  });

  describe('tags', () => {
    it('addTag emits updated array and clears input', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      fixture.componentRef.setInput('tags', ['portrait']);
      const emitted: string[][] = [];
      cmp.tagsChange.subscribe((v) => emitted.push(v));

      cmp.newTag = 'anime';
      cmp.addTag();

      expect(emitted).toEqual([['portrait', 'anime']]);
      expect(cmp.newTag).toBe('');
    });

    it('addTag ignores blank input', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      const emitted: string[][] = [];
      cmp.tagsChange.subscribe((v) => emitted.push(v));

      cmp.newTag = '';
      cmp.addTag();

      expect(emitted).toEqual([]);
    });

    it('removeTag emits filtered array', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      fixture.componentRef.setInput('tags', ['a', 'b', 'c']);
      const emitted: string[][] = [];
      cmp.tagsChange.subscribe((v) => emitted.push(v));

      cmp.removeTag('b');

      expect(emitted).toEqual([['a', 'c']]);
    });
  });

  describe('action buttons', () => {
    it('save button emits saveClicked', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      const spy = vi.fn();
      cmp.saveClicked.subscribe(spy);

      cmp.saveClicked.emit();

      expect(spy).toHaveBeenCalledTimes(1);
    });

    it('cancel button emits cancelClicked', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      const spy = vi.fn();
      cmp.cancelClicked.subscribe(spy);

      cmp.cancelClicked.emit();

      expect(spy).toHaveBeenCalledTimes(1);
    });

    it('refetch button emits refetchClicked', async () => {
      const fixture = await createFixture();
      const cmp = fixture.componentInstance;
      const spy = vi.fn();
      cmp.refetchClicked.subscribe(spy);

      cmp.refetchClicked.emit();

      expect(spy).toHaveBeenCalledTimes(1);
    });
  });
});
