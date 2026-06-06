import { Injectable, inject, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { interval, Subscription } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { NotificationService } from './notification';

interface BackendNotification {
  id: string;
  type: 'success' | 'error';
  message: string;
}

const API = '/tiny-model-manager/api';

@Injectable({ providedIn: 'root' })
export class BackendNotificationService implements OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly notif = inject(NotificationService);
  private sub: Subscription | null = null;

  start(): void {
    this.sub = interval(10_000)
      .pipe(
        switchMap(() =>
          this.http.get<{ success: boolean; data: BackendNotification[] }>(`${API}/notifications`),
        ),
      )
      .subscribe((r) => {
        if (!r.success) return;
        for (const n of r.data) {
          this.notif.show(n.type, n.message);
        }
      });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
