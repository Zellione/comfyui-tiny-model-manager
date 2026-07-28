import { TestBed } from '@angular/core/testing';
import { NotificationService } from './notification';

describe('NotificationService', () => {
  let service: NotificationService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(NotificationService);
  });

  it('show() adds a toast with the correct type and message', () => {
    service.show('success', 'Hello');
    expect(service.toasts()).toHaveLength(1);
    expect(service.toasts()[0].type).toBe('success');
    expect(service.toasts()[0].message).toBe('Hello');
  });

  it('show() supports info and warning types', () => {
    service.show('info', 'Info message');
    service.show('warning', 'Warning message');
    expect(service.toasts()[0].type).toBe('info');
    expect(service.toasts()[1].type).toBe('warning');
  });

  it('show() assigns unique incrementing ids', () => {
    service.show('success', 'A');
    service.show('error', 'B');
    const ids = service.toasts().map((t) => t.id);
    expect(ids[0]).not.toBe(ids[1]);
    expect(ids[1]).toBeGreaterThan(ids[0]);
  });

  it('multiple toasts stack in order', () => {
    service.show('success', 'first');
    service.show('error', 'second');
    service.show('success', 'third');
    expect(service.toasts()).toHaveLength(3);
    expect(service.toasts().map((t) => t.message)).toEqual(['first', 'second', 'third']);
  });

  it('dismiss() removes the toast with the matching id', () => {
    service.show('success', 'keep');
    service.show('error', 'remove');
    const removeId = service.toasts()[1].id;
    service.dismiss(removeId);
    expect(service.toasts()).toHaveLength(1);
    expect(service.toasts()[0].message).toBe('keep');
  });

  it('dismiss() is a no-op for an unknown id', () => {
    service.show('success', 'toast');
    service.dismiss(9999);
    expect(service.toasts()).toHaveLength(1);
  });
});
