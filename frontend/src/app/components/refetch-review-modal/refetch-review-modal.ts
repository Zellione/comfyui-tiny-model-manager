import {
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslatePipe } from '@ngx-translate/core';
import { interval } from 'rxjs';
import {
  ModelMeta,
  ModelService,
  RefetchApplyRequest,
  RefetchPreviewResponse,
} from '../../services/model';
import { TextDiffField } from '../text-diff-field/text-diff-field';
import { ArrayFieldMerge } from '../array-field-merge/array-field-merge';
import { ImageGalleryCompare } from '../image-gallery-compare/image-gallery-compare';

@Component({
  selector: 'app-refetch-review-modal',
  imports: [CommonModule, TextDiffField, ArrayFieldMerge, ImageGalleryCompare, TranslatePipe],
  templateUrl: './refetch-review-modal.html',
  styleUrl: './refetch-review-modal.scss',
})
export class RefetchReviewModal implements OnInit {
  data = input.required<RefetchPreviewResponse>();
  modelType = input.required<string>();
  modelPath = input.required<string>();

  applied = output<ModelMeta>();
  cancelled = output<void>();

  descriptionChoice = signal<'old' | 'new'>('old');
  baseModelChoice = signal<'old' | 'new'>('old');
  selectedTriggerWords = signal<string[]>([]);
  selectedTags = signal<string[]>([]);
  replaceImages = signal(false);
  selectedIncomingMedia = signal<string[]>([]);
  keepExistingMedia = signal<string[]>([]);
  applying = signal(false);
  expired = signal(false);
  secondsRemaining = signal<number | null>(null);

  private readonly destroyRef = inject(DestroyRef);
  private readonly modelService = inject(ModelService);

  constructor() {
    effect(() => this._applySmartDefaults());
  }

  ngOnInit() {
    this._startCountdown();
  }

  private _applySmartDefaults() {
    const d = this.data();
    this.descriptionChoice.set(d.old.description?.trim() ? 'old' : 'new');
    this.baseModelChoice.set(d.old.base_model?.trim() ? 'old' : 'new');

    const twDefault = [...d.old.trigger_words];
    if (d.old.trigger_words.length === 0) {
      twDefault.push(...d.new.trigger_words);
    }
    this.selectedTriggerWords.set(twDefault);

    const tagsDefault = [...d.old.tags];
    if (d.old.tags.length === 0) {
      tagsDefault.push(...d.new.tags);
    }
    this.selectedTags.set(tagsDefault);

    this.selectedIncomingMedia.set([...d.new.media_urls]);
    this.keepExistingMedia.set([]);
  }

  private _startCountdown() {
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        const expiry = new Date(this.data().expires_at).getTime();
        const remaining = Math.max(0, Math.floor((expiry - Date.now()) / 1000));
        this.secondsRemaining.set(remaining < 120 ? remaining : null);
        if (remaining === 0) this.expired.set(true);
      });
  }

  formatCountdown(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  private _buildApplyRequest(): RefetchApplyRequest {
    const d = this.data();
    return {
      description: this.descriptionChoice() === 'new' ? d.new.description : d.old.description,
      trigger_words: this.selectedTriggerWords(),
      tags: this.selectedTags(),
      base_model: this.baseModelChoice() === 'new' ? d.new.base_model : d.old.base_model,
      replace_media: this.replaceImages(),
      media_urls: this.replaceImages() ? this.selectedIncomingMedia() : [],
      keep_existing_media: this.replaceImages() ? this.keepExistingMedia() : [],
    };
  }

  applySelected() {
    this.applying.set(true);
    this.modelService
      .refetchApply(this.modelType(), this.modelPath(), this._buildApplyRequest())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.applying.set(false);
          if (!res.removed) this.applied.emit(res.meta);
        },
        error: (err: unknown) => {
          this.applying.set(false);
          if ((err as HttpErrorResponse).status === 410) {
            this.expired.set(true);
          }
        },
      });
  }

  @HostListener('document:keydown.escape')
  onEscapeKey() {
    this.cancelled.emit();
  }
}
