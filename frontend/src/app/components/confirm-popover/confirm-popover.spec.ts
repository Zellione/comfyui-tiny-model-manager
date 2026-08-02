import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { ConfirmPopover } from './confirm-popover';
import { PopoverService } from '../../services/popover.service';

@Component({
  template: `<app-confirm-popover [question]="q" (confirmed)="onConfirmed()">
    <button>Trigger</button>
  </app-confirm-popover>`,
  imports: [ConfirmPopover],
})
class TestHost {
  q = 'Delete it?';
  confirmed = false;
  onConfirmed() {
    this.confirmed = true;
  }
}

describe('ConfirmPopover', () => {
  let fixture: ComponentFixture<TestHost>;
  let svc: PopoverService;

  function getPanel(): HTMLElement | null {
    return fixture.nativeElement.querySelector('.cp-panel');
  }

  function getTriggerHost(): HTMLElement {
    return fixture.nativeElement.querySelector('app-confirm-popover');
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestHost],
      providers: [provideTranslateServiceForTests()],
    }).compileComponents();
    fixture = TestBed.createComponent(TestHost);
    svc = TestBed.inject(PopoverService);
    fixture.detectChanges();
  });

  it('starts closed', () => {
    expect(getPanel()).toBeNull();
  });

  it('opens on host click', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    expect(getPanel()).not.toBeNull();
  });

  it('shows the question text', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    expect(getPanel()!.querySelector('.cp-question')!.textContent).toContain('Delete it?');
  });

  it('closes on Cancel click', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    const cancel = getPanel()!.querySelector<HTMLButtonElement>('.btn-secondary')!;
    cancel.click();
    fixture.detectChanges();
    expect(getPanel()).toBeNull();
  });

  it('emits confirmed and closes on Confirm click', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    const confirm = getPanel()!.querySelector<HTMLButtonElement>('.btn-danger')!;
    confirm.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.confirmed).toBe(true);
    expect(getPanel()).toBeNull();
  });

  it('closes on Escape key', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();
    expect(getPanel()).toBeNull();
  });

  it('closes on outside click', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();
    expect(getPanel()).toBeNull();
  });

  it('does not close on panel click', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    getPanel()!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();
    expect(getPanel()).not.toBeNull();
  });

  it('only one popover open at a time', () => {
    svc.activate('other-id');
    const comp = fixture.debugElement.children[0].componentInstance as ConfirmPopover;
    expect(comp.isOpen()).toBe(false);
  });
});
