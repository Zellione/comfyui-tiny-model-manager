import { Component, OnInit } from '@angular/core';
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
  saved = false;
  error = '';

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.http.get<{ success: boolean; data: AppSettings }>(`${API}/settings`).subscribe({
      next: r => (this.settings = r.data),
      error: () => {},
    });
  }

  save() {
    this.saved = false;
    this.error = '';
    this.http.put<{ success: boolean }>(`${API}/settings`, this.settings).subscribe({
      next: () => (this.saved = true),
      error: err => (this.error = err.message),
    });
  }
}
