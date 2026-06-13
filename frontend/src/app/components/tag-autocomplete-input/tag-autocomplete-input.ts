import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { EMPTY, catchError, debounceTime, switchMap } from 'rxjs';
import { TagService } from '../../services/tags';

@Component({
  selector: 'app-tag-autocomplete-input',
  imports: [TranslatePipe],
  templateUrl: './tag-autocomplete-input.html',
  styleUrl: './tag-autocomplete-input.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TagAutocompleteInput {
  private readonly tagService = inject(TagService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly selectedTags = input<string[]>([]);
  readonly searchResultTags = input<string[]>([]);
  readonly tagAdded = output<string>();

  readonly inputValue = signal('');
  readonly open = signal(false);
  private readonly dbSuggestions = signal<string[]>([]);

  readonly suggestions = computed(() => {
    const q = this.inputValue().toLowerCase();
    const selected = new Set(this.selectedTags());
    const fromResults = this.searchResultTags().filter(
      (t) => t.toLowerCase().includes(q) && !selected.has(t),
    );
    const fromDb = this.dbSuggestions().filter((t) => !selected.has(t));
    const seen = new Set<string>();
    const merged: string[] = [];
    for (const t of [...fromResults, ...fromDb]) {
      if (!seen.has(t) && merged.length < 5) {
        seen.add(t);
        merged.push(t);
      }
    }
    return merged;
  });

  constructor() {
    toObservable(this.inputValue)
      .pipe(
        debounceTime(200),
        switchMap((q) =>
          q.length >= 1 ? this.tagService.searchTags(q).pipe(catchError(() => EMPTY)) : EMPTY,
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((tags) => this.dbSuggestions.set(tags));
  }

  onInput(v: string) {
    this.inputValue.set(v);
    this.open.set(v.length > 0);
    if (!v) this.dbSuggestions.set([]);
  }

  select(tag: string) {
    this.tagAdded.emit(tag);
    this.inputValue.set('');
    this.dbSuggestions.set([]);
    this.open.set(false);
  }

  onEnter() {
    const v = this.inputValue().trim();
    if (v) this.select(v);
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
