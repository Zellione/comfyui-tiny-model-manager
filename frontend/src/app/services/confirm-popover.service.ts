import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ConfirmPopoverService {
  private readonly _activeId = signal<string | null>(null);
  readonly activeId = this._activeId.asReadonly();

  activate(id: string) {
    this._activeId.set(id);
  }

  deactivate(id: string) {
    if (this._activeId() === id) this._activeId.set(null);
  }
}
