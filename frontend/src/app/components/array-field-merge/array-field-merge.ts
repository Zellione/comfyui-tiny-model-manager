import { Component, OnInit, computed, effect, input, model, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-array-field-merge',
  imports: [CommonModule],
  templateUrl: './array-field-merge.html',
  styleUrl: './array-field-merge.scss',
})
export class ArrayFieldMerge implements OnInit {
  oldItems = input<string[]>([]);
  newItems = input<string[]>([]);
  lastEditedAt = input<string | null>(null);
  selectedItems = model<string[]>([]);

  private _selected = signal<Set<string>>(new Set());

  readonly shared = computed(() => {
    const oldSet = new Set(this.oldItems());
    return this.newItems().filter((i) => oldSet.has(i));
  });

  readonly oldOnly = computed(() => {
    const newSet = new Set(this.newItems());
    return this.oldItems().filter((i) => !newSet.has(i));
  });

  readonly newOnly = computed(() => {
    const oldSet = new Set(this.oldItems());
    return this.newItems().filter((i) => !oldSet.has(i));
  });

  constructor() {
    // Sync internal set → two-way binding output whenever _selected changes
    effect(() => {
      this.selectedItems.set([...this._selected()]);
    });
  }

  ngOnInit() {
    this._initSelection();
  }

  private _initSelection() {
    const initial = new Set(
      this.selectedItems().length ? this.selectedItems() : this._buildDefaultSelection(),
    );
    this._selected.set(initial);
  }

  private _buildDefaultSelection(): string[] {
    const result: string[] = [];
    result.push(...this.oldOnly());
    result.push(...this.shared());
    if (this.oldItems().length === 0) {
      result.push(...this.newOnly());
    }
    return result;
  }

  isSelected(item: string): boolean {
    return this._selected().has(item);
  }

  toggle(item: string) {
    const next = new Set(this._selected());
    if (next.has(item)) {
      next.delete(item);
    } else {
      next.add(item);
    }
    this._selected.set(next);
  }
}
