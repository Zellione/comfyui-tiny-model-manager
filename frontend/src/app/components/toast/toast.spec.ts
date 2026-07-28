import { ComponentFixture, TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { ToastComponent } from './toast';
import { NotificationService } from '../../services/notification';

describe('ToastComponent', () => {
  let fixture: ComponentFixture<ToastComponent>;
  let component: ToastComponent;
  let notifService: NotificationService;

  beforeEach(async () => {
    vi.useFakeTimers();
    await TestBed.configureTestingModule({
      imports: [ToastComponent],
      providers: [provideTranslateServiceForTests(), NotificationService],
    }).compileComponents();

    notifService = TestBed.inject(NotificationService);
    fixture = TestBed.createComponent(ToastComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('toastsWithKeys', () => {
    it('maps success toast with correct duration and icon', () => {
      notifService.show('success', 'ok');
      fixture.detectChanges();
      const item = component.toastsWithKeys()[0];
      expect(item.duration).toBe(3000);
      expect(item.icon).toBe('✓');
      expect(item.progressKey).toBe(0);
    });

    it('maps error toast with correct duration and icon', () => {
      notifService.show('error', 'bad');
      fixture.detectChanges();
      const item = component.toastsWithKeys()[0];
      expect(item.duration).toBe(6000);
      expect(item.icon).toBe('✕');
    });

    it('maps info toast with correct duration and icon', () => {
      notifService.show('info', 'note');
      fixture.detectChanges();
      const item = component.toastsWithKeys()[0];
      expect(item.duration).toBe(4000);
      expect(item.icon).toBe('ℹ');
    });

    it('maps warning toast with correct duration and icon', () => {
      notifService.show('warning', 'careful');
      fixture.detectChanges();
      const item = component.toastsWithKeys()[0];
      expect(item.duration).toBe(5000);
      expect(item.icon).toBe('⚠');
    });
  });

  describe('auto-dismiss timer', () => {
    it('dismisses a success toast after 3000ms', () => {
      notifService.show('success', 'bye');
      fixture.detectChanges();
      expect(notifService.toasts()).toHaveLength(1);
      vi.advanceTimersByTime(3000);
      expect(notifService.toasts()).toHaveLength(0);
    });

    it('does not dismiss an error toast before 6000ms', () => {
      notifService.show('error', 'err');
      fixture.detectChanges();
      vi.advanceTimersByTime(5999);
      expect(notifService.toasts()).toHaveLength(1);
      vi.advanceTimersByTime(1);
      expect(notifService.toasts()).toHaveLength(0);
    });

    it('cleans up timer entry when a toast is dismissed early', () => {
      notifService.show('success', 'early');
      fixture.detectChanges();
      const id = notifService.toasts()[0].id;
      notifService.dismiss(id);
      fixture.detectChanges();
      vi.advanceTimersByTime(3000);
      expect(notifService.toasts()).toHaveLength(0);
    });
  });

  describe('pauseTimer', () => {
    it('stops auto-dismiss', () => {
      notifService.show('success', 'paused');
      fixture.detectChanges();
      const id = notifService.toasts()[0].id;
      component.pauseTimer(id);
      vi.advanceTimersByTime(3000);
      expect(notifService.toasts()).toHaveLength(1);
    });
  });

  describe('resumeTimer', () => {
    it('increments progressKey', () => {
      notifService.show('info', 'resume');
      fixture.detectChanges();
      const id = notifService.toasts()[0].id;
      component.pauseTimer(id);
      expect(component.toastsWithKeys()[0].progressKey).toBe(0);
      component.resumeTimer(id);
      fixture.detectChanges();
      expect(component.toastsWithKeys()[0].progressKey).toBe(1);
    });

    it('restarts auto-dismiss after pause', () => {
      notifService.show('success', 'resume');
      fixture.detectChanges();
      const id = notifService.toasts()[0].id;
      component.pauseTimer(id);
      vi.advanceTimersByTime(2000);
      component.resumeTimer(id);
      fixture.detectChanges();
      vi.advanceTimersByTime(2999);
      expect(notifService.toasts()).toHaveLength(1);
      vi.advanceTimersByTime(1);
      expect(notifService.toasts()).toHaveLength(0);
    });

    it('is a no-op when toast id is not found', () => {
      expect(() => component.resumeTimer(9999)).not.toThrow();
    });
  });

  describe('ngOnDestroy', () => {
    it('clears all pending timers without throwing', () => {
      notifService.show('success', 'a');
      notifService.show('error', 'b');
      fixture.detectChanges();
      expect(() => component.ngOnDestroy()).not.toThrow();
      vi.advanceTimersByTime(6000);
    });
  });
});
