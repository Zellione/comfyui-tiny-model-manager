import { BASE_MODEL_PRESETS } from './base-models';

describe('BASE_MODEL_PRESETS', () => {
  it('has no duplicates', () => {
    expect(new Set(BASE_MODEL_PRESETS).size).toBe(BASE_MODEL_PRESETS.length);
  });

  it('has no stray whitespace, which CivitAI would not match', () => {
    for (const value of BASE_MODEL_PRESETS) {
      expect(value).toBe(value.trim());
      expect(value).not.toBe('');
    }
  });

  // The families that were reported missing: an LTX / Wan / MiniMax model could not be
  // filtered for at all, and CivitAI matches the exact string, so each variant needs its
  // own entry — filtering on 'Wan Video' does not match 'Wan Video 14B t2v'.
  it.each([
    'LTXV',
    'LTXV2',
    'LTXV 2.3',
    'Wan Video',
    'Wan Video 14B t2v',
    'Wan Video 14B i2v 480p',
    'Wan Video 14B i2v 720p',
    'Wan Video 2.2 TI2V-5B',
    'Wan Video 2.2 T2V-A14B',
    'Wan Video 2.2 I2V-A14B',
    'MiniMax H3',
  ])('offers %s', (value) => {
    expect(BASE_MODEL_PRESETS).toContain(value);
  });

  // Verified against the live API as returning zero results; keeping them would hand the
  // user a filter that silently finds nothing.
  it.each(['SD 3.5', 'SD 3.5 Large', 'SDXL Turbo', 'Illustrious XL', 'NoobAI XL'])(
    'does not offer the unmatched value %s',
    (value) => {
      expect(BASE_MODEL_PRESETS).not.toContain(value);
    },
  );
});
