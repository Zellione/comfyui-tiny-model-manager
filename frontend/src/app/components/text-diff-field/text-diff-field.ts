import { Component, computed, effect, input, model } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface DiffLine {
  type: 'equal' | 'add' | 'remove';
  text: string;
}

export function diffLines(a: string, b: string): DiffLine[] {
  const aLines = a.split('\n');
  const bLines = b.split('\n');
  const n = aLines.length;
  const m = bLines.length;

  // Build LCS table
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] =
        aLines[i - 1] === bLines[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const result: DiffLine[] = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && aLines[i - 1] === bLines[j - 1]) {
      result.unshift({ type: 'equal', text: aLines[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.unshift({ type: 'add', text: bLines[j - 1] });
      j--;
    } else {
      result.unshift({ type: 'remove', text: aLines[i - 1] });
      i--;
    }
  }
  return result;
}

@Component({
  selector: 'app-text-diff-field',
  imports: [CommonModule],
  templateUrl: './text-diff-field.html',
  styleUrl: './text-diff-field.scss',
})
export class TextDiffField {
  oldValue = input<string>('');
  newValue = input<string>('');
  lastEditedAt = input<string | null>(null);
  selected = model<'old' | 'new'>('old');

  readonly diffResult = computed(() => diffLines(this.oldValue(), this.newValue()));

  readonly oldLines = computed(() =>
    this.diffResult().filter((l) => l.type === 'equal' || l.type === 'remove'),
  );

  readonly newLines = computed(() =>
    this.diffResult().filter((l) => l.type === 'equal' || l.type === 'add'),
  );

  constructor() {
    effect(() => {
      const old = this.oldValue();
      this.selected.set(old?.trim() ? 'old' : 'new');
    });
  }

  selectOld() {
    this.selected.set('old');
  }

  selectNew() {
    this.selected.set('new');
  }
}
