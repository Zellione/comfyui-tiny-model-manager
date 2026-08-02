import {
  Component,
  ElementRef,
  HostListener,
  computed,
  inject,
  input,
  model,
  signal,
} from '@angular/core';

/** Preset base models offered as suggestions. The field still accepts free text. */
export const BASE_MODEL_PRESETS = [
  'SD 1.5',
  'SD 2.1',
  'SDXL 1.0',
  'Pony',
  'Flux.1 D',
  'Flux.1 S',
  'SD 3.5',
  'SD 3.5 Large',
  'Illustrious XL',
  'NoobAI XL',
  'Hunyuan Video',
  'Krea 2',
];

/**
 * Combobox for base model selection. Unlike a native `<input list>`/`<datalist>`,
 * the chevron always reveals the full option list regardless of the current value;
 * typing filters the list. Free-text values (e.g. from CivitAI) remain allowed.
 */
@Component({
  selector: 'app-base-model-select',
  templateUrl: './base-model-select.html',
  styleUrl: './base-model-select.scss',
})
export class BaseModelSelect {
  readonly value = model<string>('');
  readonly options = input<string[]>(BASE_MODEL_PRESETS);
  readonly placeholder = input<string>('Base model');

  readonly open = signal(false);
  // null → show the full option list; string → filter the options by typed text.
  private readonly typedFilter = signal<string | null>(null);

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly filtered = computed(() => {
    const f = this.typedFilter();
    const opts = this.options();
    if (!f) return opts;
    const low = f.toLowerCase();
    return opts.filter((o) => o.toLowerCase().includes(low));
  });

  onFocus() {
    this.typedFilter.set(null);
    this.open.set(true);
  }

  toggle() {
    if (this.open()) {
      this.open.set(false);
    } else {
      this.typedFilter.set(null);
      this.open.set(true);
    }
  }

  onInput(v: string) {
    this.value.set(v);
    this.typedFilter.set(v);
    this.open.set(true);
  }

  select(option: string) {
    this.value.set(option);
    this.open.set(false);
  }

  @HostListener('document:click', ['$event'])
  onDocClick(ev: MouseEvent) {
    if (!this.host.nativeElement.contains(ev.target as Node)) {
      this.open.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    this.open.set(false);
  }
}
