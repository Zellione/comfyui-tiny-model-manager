import { TestBed } from '@angular/core/testing';
import { ArrayFieldMerge } from './array-field-merge';

async function createFixture(
  oldItems: string[] = [],
  newItems: string[] = [],
  lastEditedAt: string | null = null,
) {
  await TestBed.configureTestingModule({ imports: [ArrayFieldMerge] }).compileComponents();
  const fixture = TestBed.createComponent(ArrayFieldMerge);
  fixture.componentRef.setInput('oldItems', oldItems);
  fixture.componentRef.setInput('newItems', newItems);
  fixture.componentRef.setInput('lastEditedAt', lastEditedAt);
  fixture.detectChanges();
  return fixture;
}

describe('ArrayFieldMerge component', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('computes shared items correctly', async () => {
    const fixture = await createFixture(['a', 'b'], ['b', 'c']);
    expect(fixture.componentInstance.shared()).toEqual(['b']);
  });

  it('computes oldOnly items correctly', async () => {
    const fixture = await createFixture(['a', 'b'], ['b', 'c']);
    expect(fixture.componentInstance.oldOnly()).toEqual(['a']);
  });

  it('computes newOnly items correctly', async () => {
    const fixture = await createFixture(['a', 'b'], ['b', 'c']);
    expect(fixture.componentInstance.newOnly()).toEqual(['c']);
  });

  it('pre-selects old-only items by default', async () => {
    const fixture = await createFixture(['old-item'], ['new-item']);
    expect(fixture.componentInstance.isSelected('old-item')).toBe(true);
  });

  it('pre-selects shared items by default', async () => {
    const fixture = await createFixture(['shared'], ['shared', 'extra']);
    expect(fixture.componentInstance.isSelected('shared')).toBe(true);
  });

  it('does NOT pre-select new-only items when oldItems is non-empty', async () => {
    const fixture = await createFixture(['existing'], ['new-item']);
    expect(fixture.componentInstance.isSelected('new-item')).toBe(false);
  });

  it('pre-selects new-only items when oldItems is empty', async () => {
    const fixture = await createFixture([], ['new-item']);
    expect(fixture.componentInstance.isSelected('new-item')).toBe(true);
  });

  it('toggle() adds an unselected item', async () => {
    const fixture = await createFixture(['existing'], ['new-item']);
    const cmp = fixture.componentInstance;
    expect(cmp.isSelected('new-item')).toBe(false);
    cmp.toggle('new-item');
    expect(cmp.isSelected('new-item')).toBe(true);
  });

  it('toggle() removes a selected item', async () => {
    const fixture = await createFixture(['item'], ['item']);
    const cmp = fixture.componentInstance;
    expect(cmp.isSelected('item')).toBe(true);
    cmp.toggle('item');
    expect(cmp.isSelected('item')).toBe(false);
  });

  it('toggle() updates selectedItems output', async () => {
    const fixture = await createFixture(['existing'], ['new-item']);
    const cmp = fixture.componentInstance;
    cmp.toggle('new-item');
    fixture.detectChanges();
    expect(cmp.selectedItems()).toContain('new-item');
  });

  it('shows edited icon when lastEditedAt is set', async () => {
    const fixture = await createFixture(['a'], ['b'], '2024-01-01T00:00:00Z');
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.edited-icon')).not.toBeNull();
  });

  it('hides edited icon when lastEditedAt is null', async () => {
    const fixture = await createFixture(['a'], ['b'], null);
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.edited-icon')).toBeNull();
  });
});
