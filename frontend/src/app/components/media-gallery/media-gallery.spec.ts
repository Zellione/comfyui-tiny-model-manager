import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { MediaGallery } from './media-gallery';
import type { MediaItem } from '../../services/model';

const makeItem = (overrides: Partial<MediaItem> = {}): MediaItem => ({
  id: 1,
  media_type: 'image',
  local_path: '/media/hash/image.jpg',
  uploaded: false,
  ...overrides,
});

describe('MediaGallery', () => {
  let fixture: ComponentFixture<MediaGallery>;
  let component: MediaGallery;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MediaGallery],
      providers: [provideTranslateServiceForTests()],
    }).compileComponents();

    fixture = TestBed.createComponent(MediaGallery);
    component = fixture.componentInstance;
  });

  describe('videoPosterUrl', () => {
    it('returns a media-poster URL encoding the video path', () => {
      const url = component.videoPosterUrl('/media/hash/clip.mp4');
      expect(url).toContain('/api/media-poster/');
      expect(url).toContain(encodeURIComponent('/media/hash/clip.mp4'));
    });

    it('encodes paths with special characters', () => {
      const url = component.videoPosterUrl('/media/hash/my clip.mp4');
      expect(url).toContain(encodeURIComponent('/media/hash/my clip.mp4'));
    });
  });

  describe('onVideoPosterLoad', () => {
    it('shows the img and hides the preceding sibling', () => {
      const parent = document.createElement('div');
      const fallback = document.createElement('div');
      const img = document.createElement('img');
      parent.appendChild(fallback);
      parent.appendChild(img);

      const event = { target: img } as unknown as Event;
      component.onVideoPosterLoad(event);

      expect(img.style.display).toBe('block');
      expect(fallback.style.display).toBe('none');
    });

    it('shows the img even when there is no previous sibling', () => {
      const img = document.createElement('img');
      const event = { target: img } as unknown as Event;
      component.onVideoPosterLoad(event);
      expect(img.style.display).toBe('block');
    });
  });

  describe('template', () => {
    it('renders the poster wrapper for video thumbnails', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 1, media_type: 'video', local_path: '/media/hash/clip.mp4' }),
        makeItem({ id: 2, media_type: 'image', local_path: '/media/hash/img.jpg' }),
      ]);
      fixture.detectChanges();

      const wrap = fixture.nativeElement.querySelector('.gallery-thumb-video-wrap');
      expect(wrap).not.toBeNull();

      const fallback = wrap.querySelector('.gallery-thumb-video');
      expect(fallback).not.toBeNull();

      const posterImg = wrap.querySelector('img');
      expect(posterImg).not.toBeNull();
      expect(posterImg.src).toContain('/api/media-poster/');
    });

    it('adds [poster] attribute to the video element in the main panel', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 1, media_type: 'video', local_path: '/media/hash/clip.mp4' }),
      ]);
      fixture.detectChanges();

      const video: HTMLVideoElement = fixture.nativeElement.querySelector('video');
      expect(video).not.toBeNull();
      expect(video.getAttribute('poster')).toContain('/api/media-poster/');
    });
  });

  describe('urls input', () => {
    it('normalises remote URLs, detecting videos by extension', () => {
      fixture.componentRef.setInput('urls', [
        'https://cdn.example/img.jpeg',
        'https://cdn.example/clip.mp4',
      ]);
      fixture.detectChanges();

      expect(component.items()).toEqual([
        {
          src: 'https://cdn.example/img.jpeg',
          isVideo: false,
          poster: null,
          uploaded: false,
          mediaId: 0,
          localPath: '',
        },
        {
          src: 'https://cdn.example/clip.mp4',
          isVideo: true,
          poster: null,
          uploaded: false,
          mediaId: 0,
          localPath: '',
        },
      ]);
    });

    it('renders remote URLs verbatim, without the local media route', () => {
      fixture.componentRef.setInput('urls', ['https://cdn.example/img.jpeg']);
      fixture.detectChanges();

      const img: HTMLImageElement = fixture.nativeElement.querySelector('.gallery-main img');
      expect(img.getAttribute('src')).toBe('https://cdn.example/img.jpeg');
    });

    it('omits the poster img for remote video thumbnails, keeping the ▶ fallback', () => {
      fixture.componentRef.setInput('urls', [
        'https://cdn.example/clip.mp4',
        'https://cdn.example/img.jpeg',
      ]);
      fixture.detectChanges();

      const wrap = fixture.nativeElement.querySelector('.gallery-thumb-video-wrap');
      expect(wrap.querySelector('.gallery-thumb-video')).not.toBeNull();
      expect(wrap.querySelector('img')).toBeNull();
    });

    it('leaves [poster] unset on a remote main video', () => {
      fixture.componentRef.setInput('urls', ['https://cdn.example/clip.mp4']);
      fixture.detectChanges();

      const video: HTMLVideoElement = fixture.nativeElement.querySelector('video');
      expect(video.getAttribute('poster')).toBeNull();
    });

    it('prefers media over urls when both are supplied', () => {
      fixture.componentRef.setInput('media', [makeItem()]);
      fixture.componentRef.setInput('urls', ['https://cdn.example/img.jpeg']);
      fixture.detectChanges();

      expect(component.items()).toHaveLength(1);
      expect(component.items()[0].src).toContain('/api/media/');
    });

    it('falls back to urls when media is empty', () => {
      fixture.componentRef.setInput('media', []);
      fixture.componentRef.setInput('urls', ['https://cdn.example/img.jpeg']);
      fixture.detectChanges();

      expect(component.items()[0].src).toBe('https://cdn.example/img.jpeg');
    });

    it('shows the placeholder when neither input has media', () => {
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.gallery-placeholder')).not.toBeNull();
    });
  });

  describe('galleryIdx', () => {
    it('resets to the first item when pointed at a different list', () => {
      fixture.componentRef.setInput('urls', ['a.jpeg', 'b.jpeg', 'c.jpeg']);
      fixture.detectChanges();
      component.galleryIdx.set(2);
      expect(component.activeMedia()?.src).toBe('c.jpeg');

      fixture.componentRef.setInput('urls', ['x.jpeg', 'y.jpeg']);
      fixture.detectChanges();

      expect(component.galleryIdx()).toBe(0);
      expect(component.activeMedia()?.src).toBe('x.jpeg');
    });

    it('keeps the selection when the input is re-set to the same content', () => {
      fixture.componentRef.setInput('urls', ['a.jpeg', 'b.jpeg']);
      fixture.detectChanges();
      component.galleryIdx.set(1);

      // A fresh array with identical contents — what a parent method binding produces.
      fixture.componentRef.setInput('urls', ['a.jpeg', 'b.jpeg']);
      fixture.detectChanges();

      expect(component.galleryIdx()).toBe(1);
    });

    it('clamps the active item when the list shrinks', () => {
      fixture.componentRef.setInput('urls', ['a.jpeg', 'b.jpeg', 'c.jpeg']);
      fixture.detectChanges();
      component.galleryIdx.set(2);

      fixture.componentRef.setInput('urls', ['a.jpeg']);
      fixture.detectChanges();

      expect(component.activeMedia()?.src).toBe('a.jpeg');
    });
  });

  describe('lightbox', () => {
    it('opens for images and closes on Escape', () => {
      fixture.componentRef.setInput('urls', ['https://cdn.example/img.jpeg']);
      fixture.detectChanges();

      component.lightboxOpen.set(true);
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.lightbox')).not.toBeNull();

      component.onEscape();
      fixture.detectChanges();
      expect(component.lightboxOpen()).toBe(false);
      expect(fixture.nativeElement.querySelector('.lightbox')).toBeNull();
    });

    it('does not render for a video item', () => {
      fixture.componentRef.setInput('urls', ['https://cdn.example/clip.mp4']);
      fixture.detectChanges();

      component.lightboxOpen.set(true);
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.lightbox')).toBeNull();
    });
  });

  describe('upload affordances', () => {
    it('hides the upload zone when uploadable is false', () => {
      fixture.componentRef.setInput('media', []);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(false);
    });

    it('shows the upload zone for an empty gallery when uploadable', () => {
      fixture.componentRef.setInput('media', []);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(true);
    });

    it('shows the upload zone while every item is an upload', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 1, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
      ]);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(true);
      expect(fixture.nativeElement.querySelector('app-media-upload-zone')).not.toBeNull();
    });

    it('hides the upload zone once a fetched image is present', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 1, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
        makeItem({ id: 2, local_path: '/m/h/0.jpg', uploaded: false }),
      ]);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(false);
      expect(fixture.nativeElement.querySelector('app-media-upload-zone')).toBeNull();
    });

    it('never shows the upload zone for remote urls', () => {
      fixture.componentRef.setInput('urls', ['https://example.test/a.jpg']);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(false);
      expect(component.items()[0].uploaded).toBe(false);
    });

    it('carries mediaId and localPath on each local item', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 42, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
      ]);
      fixture.detectChanges();

      expect(component.items()[0].mediaId).toBe(42);
      expect(component.items()[0].localPath).toBe('/m/h/upload-0123456789ab.png');
    });

    it('re-emits a remove request for the given item', () => {
      const emitted: unknown[] = [];
      fixture.componentRef.setInput('media', [
        makeItem({ id: 42, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
      ]);
      fixture.detectChanges();
      component.removeRequested.subscribe((v) => emitted.push(v));

      component.requestRemove(component.items()[0]);

      expect(emitted.length).toBe(1);
      expect((emitted[0] as { mediaId: number }).mediaId).toBe(42);
    });

    it('re-emits selected files', () => {
      const emitted: File[][] = [];
      component.filesSelected.subscribe((f) => emitted.push(f));

      component.onFilesSelected([new File(['a'], 'a.png', { type: 'image/png' })]);

      expect(emitted.length).toBe(1);
    });
  });
});
