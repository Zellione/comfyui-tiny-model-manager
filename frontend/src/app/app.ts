import { Component, OnInit, signal, inject, DestroyRef } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ToastComponent } from './components/toast/toast';
import { NotificationService } from './services/notification';
import { DownloadService } from './services/download';
import { BackendNotificationService } from './services/backend-notification';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ToastComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  isDark = signal(true);

  private notifService = inject(NotificationService);
  private dlService = inject(DownloadService);
  private backendNotif = inject(BackendNotificationService);
  private destroyRef = inject(DestroyRef);

  ngOnInit() {
    this.backendNotif.start();
    const stored = localStorage.getItem('theme');
    const dark = stored !== 'light';
    this.isDark.set(dark);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');

    this.dlService.completedTasks$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((task) => {
      if (task.status === 'done') {
        this.notifService.show('success', `Download complete: ${task.filename}`);
      } else {
        this.notifService.show(
          'error',
          `Download failed: ${task.filename}${task.error ? ' — ' + task.error : ''}`,
        );
      }
    });
  }

  toggleTheme() {
    const next = !this.isDark();
    this.isDark.set(next);
    document.documentElement.setAttribute('data-theme', next ? 'dark' : 'light');
    localStorage.setItem('theme', next ? 'dark' : 'light');
  }
}
