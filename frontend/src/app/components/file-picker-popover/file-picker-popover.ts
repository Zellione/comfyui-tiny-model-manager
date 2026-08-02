import { Component, input, output } from '@angular/core';
import { PopoverTrigger } from '../popover-trigger';

// Minimal structural shape of a pickable file. Both `InstalledFile` and `RepoFile`
// satisfy it, so the popover works with either without importing their types.
export interface PickableFile {
  filename: string;
  model_type: string;
}

@Component({
  selector: 'app-file-picker-popover',
  templateUrl: './file-picker-popover.html',
  styleUrl: './file-picker-popover.scss',
})
export class FilePickerPopover extends PopoverTrigger {
  readonly heading = input<string>('');
  readonly files = input<PickableFile[]>([]);
  readonly picked = output<PickableFile>();

  basename(path: string): string {
    return path.split('/').pop() ?? path;
  }

  // "<model_type> · <subfolder>", or just the type when the file sits at the root.
  subLabel(file: PickableFile): string {
    const subfolder = file.filename.includes('/')
      ? file.filename.split('/').slice(0, -1).join('/')
      : '';
    return subfolder ? `${file.model_type} · ${subfolder}` : file.model_type;
  }

  onPick(ev: MouseEvent, file: PickableFile) {
    ev.stopPropagation();
    this.close();
    this.picked.emit(file);
  }
}
