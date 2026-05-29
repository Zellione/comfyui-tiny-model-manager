import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should start in dark mode', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance.isDark()).toBe(true);
  });

  it('should toggle theme from dark to light', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    app.toggleTheme();
    expect(app.isDark()).toBe(false);
  });

  it('should toggle theme back to dark', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    app.toggleTheme(); // dark → light
    app.toggleTheme(); // light → dark
    expect(app.isDark()).toBe(true);
  });

  it('should render a theme toggle button', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const btn = (fixture.nativeElement as HTMLElement).querySelector('.icon-btn');
    expect(btn).toBeTruthy();
  });
});
