import { Component, OnInit, ChangeDetectorRef, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

interface AppSettings {
  civitai_api_key: string;
  hf_token: string;
  media_dir: string;
}

const API = '/tiny-model-manager/api';

@Component({
  selector: 'app-settings',
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings implements OnInit {
  settings: AppSettings = { civitai_api_key: '', hf_token: '', media_dir: '' };
  saved = signal(false);
  error = signal('');

  constructor(private http: HttpClient, private cdr: ChangeDetectorRef) {}

  ngOnInit() {
    this.http.get<{ success: boolean; data: AppSettings }>(`${API}/settings`).subscribe({
      next: r => { this.settings = r.data; this.cdr.markForCheck(); },
      error: () => {},
    });
  }

  save() {
    this.saved.set(false);
    this.error.set('');
    this.http.put<{ success: boolean }>(`${API}/settings`, this.settings).subscribe({
      next: () => this.saved.set(true),
      error: err => this.error.set((err as Error).message),
    });
  }
}
