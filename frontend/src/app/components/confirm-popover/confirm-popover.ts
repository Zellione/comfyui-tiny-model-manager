import {
  Component,
  ElementRef,
  HostListener,
  computed,
  inject,
  input,
  output,
} from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ConfirmPopoverService } from '../../services/confirm-popover.service';

@Component({
  selector: 'app-confirm-popover',
  imports: [TranslatePipe],
  templateUrl: './confirm-popover.html',
  styleUrl: './confirm-popover.scss',
})
export class ConfirmPopover {
  readonly question = input<string>('Are you sure?');
  readonly confirmed = output<void>();

  readonly id = crypto.randomUUID();

  private readonly service = inject(ConfirmPopoverService);
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

  onConfirm(ev: MouseEvent) {
    ev.stopPropagation();
    this.service.deactivate(this.id);
    this.confirmed.emit();
  }

  onCancel(ev: MouseEvent) {
    ev.stopPropagation();
    this.service.deactivate(this.id);
  }
}
