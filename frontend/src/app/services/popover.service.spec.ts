import { TestBed } from '@angular/core/testing';
import { PopoverService } from './popover.service';

describe('PopoverService', () => {
  let svc: PopoverService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    svc = TestBed.inject(PopoverService);
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
