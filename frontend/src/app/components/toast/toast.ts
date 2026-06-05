import { Component, inject, effect, OnDestroy } from '@angular/core';
import { NotificationService, Toast } from '../../services/notification';

const DURATIONS: Record<Toast['type'], number> = { success: 3000, error: 6000 };

@Component({
  selector: 'app-toast',
  templateUrl: './toast.html',
  styleUrl: './toast.scss',
})
export class ToastComponent implements OnDestroy {
  readonly notifService = inject(NotificationService);
  private readonly timers = new Map<number, ReturnType<typeof setTimeout>>();

  constructor() {
    effect(() => {
      const current = new Set(this.notifService.toasts().map((t) => t.id));
      for (const toast of this.notifService.toasts()) {
        if (!this.timers.has(toast.id)) {
          this.startTimer(toast.id, toast.type);
        }
      }
      for (const id of this.timers.keys()) {
        if (!current.has(id)) {
          clearTimeout(this.timers.get(id));
          this.timers.delete(id);
        }
      }
    });
  }

  ngOnDestroy() {
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
  }

  pauseTimer(id: number): void {
    clearTimeout(this.timers.get(id));
    this.timers.delete(id);
  }

  resumeTimer(id: number): void {
    const toast = this.notifService.toasts().find((t) => t.id === id);
    if (toast) this.startTimer(id, toast.type);
  }

  private startTimer(id: number, type: Toast['type']): void {
    this.timers.set(
      id,
      setTimeout(() => this.notifService.dismiss(id), DURATIONS[type]),
    );
  }
}
