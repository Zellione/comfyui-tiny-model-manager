import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { MediaGallery } from './media-gallery';
import type { MediaItem } from '../../services/model';

const makeItem = (overrides: Partial<MediaItem> = {}): MediaItem => ({
  id: 1,
  media_type: 'image',
  local_path: '/media/hash/image.jpg',
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
    it('replaces extension with _poster.jpg and passes through mediaUrl', () => {
      const url = component.videoPosterUrl('/media/hash/clip.mp4');
      expect(url).toContain('_poster.jpg');
      expect(url).not.toContain('.mp4');
    });

    it('works when the path has no extension', () => {
      const url = component.videoPosterUrl('/media/hash/clip');
      expect(url).toContain('clip_poster.jpg');
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
      expect(posterImg.src).toContain('_poster.jpg');
    });

    it('adds [poster] attribute to the video element in the main panel', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 1, media_type: 'video', local_path: '/media/hash/clip.mp4' }),
      ]);
      fixture.detectChanges();

      const video: HTMLVideoElement = fixture.nativeElement.querySelector('video');
      expect(video).not.toBeNull();
      expect(video.getAttribute('poster')).toContain('_poster.jpg');
    });
  });
});
