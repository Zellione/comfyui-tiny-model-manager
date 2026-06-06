import { TestBed } from '@angular/core/testing';
import { ConfirmPopoverService } from './confirm-popover.service';

describe('ConfirmPopoverService', () => {
  let svc: ConfirmPopoverService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    svc = TestBed.inject(ConfirmPopoverService);
  });

  it('starts with no active id', () => {
    expect(svc.activeId()).toBeNull();
  });

  it('activates an id', () => {
    svc.activate('a');
    expect(svc.activeId()).toBe('a');
  });

  it('replacing activation closes the previous id', () => {
    svc.activate('a');
    svc.activate('b');
    expect(svc.activeId()).toBe('b');
  });

  it('deactivates only when the id matches', () => {
    svc.activate('a');
    svc.deactivate('b');
    expect(svc.activeId()).toBe('a');
    svc.deactivate('a');
    expect(svc.activeId()).toBeNull();
  });
});
