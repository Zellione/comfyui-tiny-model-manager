import { describe, expect, it } from 'vitest';
import { hideOnError, showOnLoad, showPosterOnLoad, videoPosterUrl } from './media-events';

function imgEvent(): { img: HTMLImageElement; event: Event } {
  const img = document.createElement('img');
  const event = new Event('load');
  Object.defineProperty(event, 'target', { value: img });
  return { img, event };
}

describe('media-events', () => {
  describe('showOnLoad', () => {
    it('reveals the image', () => {
      const { img, event } = imgEvent();
      img.style.display = 'none';
      showOnLoad(event);
      expect(img.style.display).toBe('block');
    });
  });

  describe('hideOnError', () => {
    it('hides the image', () => {
      const { img, event } = imgEvent();
      img.style.display = 'block';
      hideOnError(event);
      expect(img.style.display).toBe('none');
    });
  });

  describe('showPosterOnLoad', () => {
    it('reveals the poster and hides the preceding ▶ fallback sibling', () => {
      const wrap = document.createElement('div');
      const fallback = document.createElement('div');
      const img = document.createElement('img');
      img.style.display = 'none';
      wrap.append(fallback, img);
      const event = new Event('load');
      Object.defineProperty(event, 'target', { value: img });

      showPosterOnLoad(event);

      expect(img.style.display).toBe('block');
      expect(fallback.style.display).toBe('none');
    });

    it('tolerates a poster without a preceding sibling', () => {
      const { img, event } = imgEvent();
      showPosterOnLoad(event);
      expect(img.style.display).toBe('block');
    });
  });

  describe('videoPosterUrl', () => {
    it('builds the media-poster route with an encoded path', () => {
      expect(videoPosterUrl('sub dir/clip.mp4')).toBe(
        '/tiny-model-manager/api/media-poster/sub%20dir%2Fclip.mp4',
      );
    });
  });
});
