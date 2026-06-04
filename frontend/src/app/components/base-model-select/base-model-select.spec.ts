import { TestBed } from '@angular/core/testing';
import { BaseModelSelect, BASE_MODEL_PRESETS } from './base-model-select';

async function createFixture() {
  await TestBed.configureTestingModule({ imports: [BaseModelSelect] }).compileComponents();
  const fixture = TestBed.createComponent(BaseModelSelect);
  fixture.detectChanges();
  return fixture;
}

describe('BaseModelSelect component', () => {
  afterEach(() => TestBed.resetTestingModule());

  it('creates successfully', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('shows the full option list when opened, regardless of current value', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.value.set('Illustrious'); // a free-text value not in the presets
    cmp.toggle();
    expect(cmp.open()).toBe(true);
    expect(cmp.filtered()).toEqual(BASE_MODEL_PRESETS);
  });

  it('filters options when typing', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('flux');
    expect(cmp.filtered()).toEqual(['Flux.1 D', 'Flux.1 S']);
    expect(cmp.value()).toBe('flux');
  });

  it('selecting an option sets value and closes', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.toggle();
    cmp.select('Pony');
    expect(cmp.value()).toBe('Pony');
    expect(cmp.open()).toBe(false);
  });

  it('focus opens with the full list even after a prior filter', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.onInput('sd');
    expect(cmp.filtered().length).toBeLessThan(BASE_MODEL_PRESETS.length);
    cmp.onFocus();
    expect(cmp.filtered()).toEqual(BASE_MODEL_PRESETS);
  });

  it('escape closes the panel', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    cmp.toggle();
    expect(cmp.open()).toBe(true);
    cmp.onEscape();
    expect(cmp.open()).toBe(false);
  });

  it('respects custom options input', async () => {
    const fixture = await createFixture();
    const cmp = fixture.componentInstance;
    fixture.componentRef.setInput('options', ['Custom A', 'Custom B']);
    cmp.toggle();
    expect(cmp.filtered()).toEqual(['Custom A', 'Custom B']);
  });
});
