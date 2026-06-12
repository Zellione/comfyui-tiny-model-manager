import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
}

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private _id = 0;
  readonly toasts = signal<Toast[]>([]);

  show(type: Toast['type'], message: string): void {
    this.toasts.update((t) => [...t, { id: ++this._id, type, message }]);
  }

  dismiss(id: number): void {
    this.toasts.update((t) => t.filter((x) => x.id !== id));
  }
}
