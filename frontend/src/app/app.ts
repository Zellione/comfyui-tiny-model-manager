import { Component, OnInit, signal, inject, DestroyRef } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { ToastComponent } from './components/toast/toast';
import { NotificationService } from './services/notification';
import { DownloadService } from './services/download';
import { BackendNotificationService } from './services/backend-notification';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ToastComponent, TranslatePipe],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  isDark = signal(true);

  private readonly notifService = inject(NotificationService);
  private readonly dlService = inject(DownloadService);
  private readonly backendNotif = inject(BackendNotificationService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly translate = inject(TranslateService);

  ngOnInit() {
    this.backendNotif.start();
    const stored = localStorage.getItem('theme');
    const dark = stored !== 'light';
    this.isDark.set(dark);
    document.documentElement.dataset['theme'] = dark ? 'dark' : 'light';

    this.dlService.completedTasks$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((task) => {
      if (task.status === 'done') {
        this.notifService.show(
          'success',
          this.translate.instant('app.download_complete', { filename: task.filename }),
        );
      } else if (task.error_code === 'early_access') {
        this.notifService.show(
          'error',
          this.translate.instant('app.download_failed_early_access', {
            filename: task.filename,
          }),
        );
      } else if (task.error_code === 'login_required') {
        this.notifService.show(
          'error',
          this.translate.instant('app.download_failed_login_required', {
            filename: task.filename,
          }),
        );
      } else if (task.error) {
        this.notifService.show(
          'error',
          this.translate.instant('app.download_failed_with_error', {
            filename: task.filename,
            error: task.error,
          }),
        );
      } else {
        this.notifService.show(
          'error',
          this.translate.instant('app.download_failed', { filename: task.filename }),
        );
      }
    });
  }

  toggleTheme() {
    const next = !this.isDark();
    this.isDark.set(next);
    document.documentElement.dataset['theme'] = next ? 'dark' : 'light';
    localStorage.setItem('theme', next ? 'dark' : 'light');
  }
}
