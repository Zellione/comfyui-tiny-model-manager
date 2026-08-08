import { ComponentFixture, TestBed } from '@angular/core/testing';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { MAX_FILE_BYTES, MAX_FILES, MediaUploadZone } from './media-upload-zone';

const makeFile = (name: string, type: string, size = 10): File => {
  const file = new File([new Uint8Array(size)], name, { type });
  return file;
};

describe('MediaUploadZone', () => {
  let fixture: ComponentFixture<MediaUploadZone>;
  let component: MediaUploadZone;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MediaUploadZone],
      providers: [provideTranslateServiceForTests()],
    }).compileComponents();

    fixture = TestBed.createComponent(MediaUploadZone);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('emits the accepted files', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('a.png', 'image/png'), makeFile('b.jpg', 'image/jpeg')]);

    expect(emitted).toHaveLength(1);
    expect(emitted[0].map((f) => f.name)).toEqual(['a.png', 'b.jpg']);
    expect(component.localError()).toBe('');
  });

  it('rejects an unsupported type and emits nothing', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('a.pdf', 'application/pdf')]);

    expect(emitted).toHaveLength(0);
    expect(component.localError()).toBe('media_gallery.upload_error_type');
  });

  it('rejects a file over the size cap', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('big.png', 'image/png', MAX_FILE_BYTES + 1)]);

    expect(emitted).toHaveLength(0);
    expect(component.localError()).toBe('media_gallery.upload_error_size');
  });

  it('rejects more than MAX_FILES at once', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept(
      Array.from({ length: MAX_FILES + 1 }, (_, i) => makeFile(`f${i}.png`, 'image/png')),
    );

    expect(emitted).toHaveLength(0);
    expect(component.localError()).toBe('media_gallery.upload_error_count');
  });

  it('ignores an empty selection', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([]);

    expect(emitted).toHaveLength(0);
  });

  it('does not accept files while busy', () => {
    const emitted: File[][] = [];
    fixture.componentRef.setInput('busy', true);
    fixture.detectChanges();
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('a.png', 'image/png')]);

    expect(emitted).toHaveLength(0);
  });

  it('tracks the drag state', () => {
    const over = {
      preventDefault: vi.fn(),
    } as unknown as DragEvent;
    component.onDragOver(over);
    expect(component.dragging()).toBe(true);

    component.onDragLeave();
    expect(component.dragging()).toBe(false);
  });
});
