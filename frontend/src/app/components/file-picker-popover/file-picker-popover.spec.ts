import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';
import { FilePickerPopover, PickableFile } from './file-picker-popover';
import { PopoverService } from '../../services/popover.service';

@Component({
  template: `<app-file-picker-popover
    [heading]="heading"
    [files]="files"
    (picked)="onPicked($event)"
  >
    <button>Trigger</button>
  </app-file-picker-popover>`,
  imports: [FilePickerPopover],
})
class TestHost {
  heading = 'Choose a file';
  files: PickableFile[] = [
    { filename: 'model-a.safetensors', model_type: 'loras' },
    { filename: 'sdxl/model-b.safetensors', model_type: 'checkpoints' },
  ];
  pickedFile: PickableFile | null = null;
  onPicked(file: PickableFile) {
    this.pickedFile = file;
  }
}

describe('FilePickerPopover', () => {
  let fixture: ComponentFixture<TestHost>;
  let svc: PopoverService;

  function getPanel(): HTMLElement | null {
    return fixture.nativeElement.querySelector('.fp-panel');
  }

  function getItems(): HTMLButtonElement[] {
    const root = fixture.nativeElement as HTMLElement;
    return Array.from(root.querySelectorAll<HTMLButtonElement>('.fp-item'));
  }

  function getTriggerHost(): HTMLElement {
    return fixture.nativeElement.querySelector('app-file-picker-popover');
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [TestHost] }).compileComponents();
    fixture = TestBed.createComponent(TestHost);
    svc = TestBed.inject(PopoverService);
    fixture.detectChanges();
  });

  it('starts closed', () => {
    expect(getPanel()).toBeNull();
  });

  it('opens on host click and shows the heading', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    expect(getPanel()).not.toBeNull();
    expect(getPanel()!.querySelector('.fp-heading')!.textContent).toContain('Choose a file');
  });

  it('renders one row per file with basename and sub-label', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    const items = getItems();
    expect(items.length).toBe(2);
    expect(items[0].querySelector('.fp-item-name')!.textContent).toContain('model-a.safetensors');
    expect(items[0].querySelector('.fp-item-sub')!.textContent).toContain('loras');
    expect(items[1].querySelector('.fp-item-name')!.textContent).toContain('model-b.safetensors');
    expect(items[1].querySelector('.fp-item-sub')!.textContent).toContain('checkpoints · sdxl');
  });

  it('emits the picked file and closes on row click', () => {
    getTriggerHost().click();
    fixture.detectChanges();
    getItems()[1].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.pickedFile).toEqual({
      filename: 'sdxl/model-b.safetensors',
      model_type: 'checkpoints',
    });
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

  it('omits the heading element when no heading is given', () => {
    // A fresh fixture: flipping the input on the already-checked one would trip NG0100.
    fixture.destroy();
    fixture = TestBed.createComponent(TestHost);
    fixture.componentInstance.heading = '';
    fixture.detectChanges();
    getTriggerHost().click();
    fixture.detectChanges();
    expect(getPanel()!.querySelector('.fp-heading')).toBeNull();
  });

  it('only one popover open at a time', () => {
    svc.activate('other-id');
    const comp = fixture.debugElement.children[0].componentInstance as FilePickerPopover;
    expect(comp.isOpen()).toBe(false);
  });
});
