import {
  Component,
  ElementRef,
  HostListener,
  computed,
  inject,
  input,
  output,
} from '@angular/core';
import { PopoverService } from '../../services/popover.service';

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
export class FilePickerPopover {
  readonly heading = input<string>('');
  readonly files = input<PickableFile[]>([]);
  readonly picked = output<PickableFile>();

  readonly id = crypto.randomUUID();

  private readonly service = inject(PopoverService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly isOpen = computed(() => this.service.activeId() === this.id);

  @HostListener('click')
  onHostClick() {
    if (this.isOpen()) {
      this.service.deactivate(this.id);
    } else {
      this.service.activate(this.id);
    }
  }

  @HostListener('document:click', ['$event'])
  onDocClick(ev: MouseEvent) {
    if (
      this.isOpen() &&
      ev.target instanceof Node &&
      !this.host.nativeElement.contains(ev.target)
    ) {
      this.service.deactivate(this.id);
    }
  }

  @HostListener('document:keydown.escape')
  onEscape() {
    this.service.deactivate(this.id);
  }

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
    this.service.deactivate(this.id);
    this.picked.emit(file);
  }
}
