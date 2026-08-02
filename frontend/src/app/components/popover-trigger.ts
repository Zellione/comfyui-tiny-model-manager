import { Directive, ElementRef, HostListener, computed, inject } from '@angular/core';
import { PopoverService } from '../services/popover.service';

// Shared open/close plumbing for popovers that hang off a projected trigger element:
// clicking the host toggles the panel, only one popover is open at a time (the id is
// registered with PopoverService), and an outside click or Escape closes it.
//
// Subclasses supply the panel markup and gate it on `isOpen()`; they call `close()` once
// their action has been chosen.
@Directive()
export abstract class PopoverTrigger {
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

  protected close() {
    this.service.deactivate(this.id);
  }
}
