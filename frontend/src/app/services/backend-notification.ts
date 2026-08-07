import { Injectable, inject, DestroyRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { interval, of } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { NotificationService } from './notification';

interface BackendNotification {
  id: string;
  type: 'success' | 'error';
  message: string;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class BackendNotificationService {
  private readonly http = inject(HttpClient);
  private readonly notif = inject(NotificationService);
  private readonly destroyRef = inject(DestroyRef);

  start(): void {
    interval(10_000)
      .pipe(
        switchMap(() =>
          this.http
            .get<{ success: boolean; data: BackendNotification[] }>(`${API}/notifications`)
            .pipe(catchError(() => of({ success: false, data: [] as BackendNotification[] }))),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((r) => {
        if (!r.success) return;
        for (const n of r.data) {
          this.notif.show(n.type, n.message);
        }
      });
  }
}
