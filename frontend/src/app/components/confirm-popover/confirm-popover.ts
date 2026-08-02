import { Component, input, output } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { PopoverTrigger } from '../popover-trigger';

@Component({
  selector: 'app-confirm-popover',
  imports: [TranslatePipe],
  templateUrl: './confirm-popover.html',
  styleUrl: './confirm-popover.scss',
})
export class ConfirmPopover extends PopoverTrigger {
  readonly question = input<string>('Are you sure?');
  readonly confirmed = output<void>();

  onConfirm(ev: MouseEvent) {
    ev.stopPropagation();
    this.close();
    this.confirmed.emit();
  }

  onCancel(ev: MouseEvent) {
    ev.stopPropagation();
    this.close();
  }
}
