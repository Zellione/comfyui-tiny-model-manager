import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-edit-meta-form',
  templateUrl: './edit-meta-form.html',
  styleUrl: './edit-meta-form.scss',
  imports: [FormsModule],
})
export class EditMetaForm {
  readonly triggerWords = input<string[]>([]);
  readonly tags = input<string[]>([]);
  readonly saving = input(false);
  readonly refetching = input(false);

  readonly triggerWordsChange = output<string[]>();
  readonly tagsChange = output<string[]>();
  readonly saveClicked = output<void>();
  readonly cancelClicked = output<void>();
  readonly refetchClicked = output<void>();

  newTriggerWord = '';
  newTag = '';

  addTriggerWord() {
    const w = this.newTriggerWord.trim();
    if (!w) return;
    this.triggerWordsChange.emit([...this.triggerWords(), w]);
    this.newTriggerWord = '';
  }

  removeTriggerWord(word: string) {
    this.triggerWordsChange.emit(this.triggerWords().filter((w) => w !== word));
  }

  addTag() {
    const t = this.newTag.trim();
    if (!t) return;
    this.tagsChange.emit([...this.tags(), t]);
    this.newTag = '';
  }

  removeTag(tag: string) {
    this.tagsChange.emit(this.tags().filter((t) => t !== tag));
  }
}
