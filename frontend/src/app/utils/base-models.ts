/**
 * CivitAI's `baseModels` vocabulary.
 *
 * These strings are used two ways, and both need CivitAI's exact spelling:
 *  - as the `baseModels` search filter, where a typo silently returns zero results
 *    rather than an error;
 *  - as suggestions when tagging a local model, so a stored `base_model` matches what
 *    CivitAI would have reported for the same file.
 *
 * The field still accepts free text, so a value missing here is inconvenient, not fatal.
 *
 * Verified against the live API (`/api/v1/models`) by harvesting `modelVersions[].baseModel`
 * across ~40 queries and probing each value with `?baseModels=`. Entries that returned nothing
 * were dropped: `SD 3.5`, `SD 3.5 Large`, `SDXL Turbo`, `Illustrious XL` and `NoobAI XL` had all
 * silently stopped matching. **Re-harvest rather than hand-adding** when this list goes stale —
 * guessing is what put the broken entries here.
 */
export const BASE_MODEL_PRESETS = [
  // Stable Diffusion
  'SD 1.4',
  'SD 1.5',
  'SD 1.5 LCM',
  'SD 1.5 Hyper',
  'SD 2.0',
  'SD 2.1',
  'SD 2.1 768',
  'SDXL 0.9',
  'SDXL 1.0',
  'SDXL 1.0 LCM',
  'SDXL Lightning',
  'SDXL Hyper',
  'Stable Cascade',
  // Anime / illustration finetunes
  'Pony',
  'Pony V7',
  'Illustrious',
  'NoobAI',
  'Anima',
  // Flux
  'Flux.1 D',
  'Flux.1 S',
  'Flux.1 Kontext',
  'Flux.1 Krea',
  'Flux.2 D',
  'Flux.2 Klein 4B',
  'Flux.2 Klein 4B-base',
  'Flux.2 Klein 9B',
  'Flux.2 Klein 9B-base',
  'Krea 2',
  // Other image models
  'Qwen',
  'Qwen 2',
  'ZImageBase',
  'ZImageTurbo',
  'Chroma',
  'HiDream',
  'HiDream-O1',
  'Hunyuan 1',
  'Kolors',
  'Lumina',
  'PixArt a',
  'PixArt E',
  'Ernie',
  'Seedream',
  'Ideogram 4.0',
  'Lens',
  'MageFlow',
  'ODOR',
  // Video
  'LTXV',
  'LTXV2',
  'LTXV 2.3',
  'Wan Video',
  'Wan Video 1.3B t2v',
  'Wan Video 14B t2v',
  'Wan Video 14B i2v 480p',
  'Wan Video 14B i2v 720p',
  'Wan Video 2.2 TI2V-5B',
  'Wan Video 2.2 T2V-A14B',
  'Wan Video 2.2 I2V-A14B',
  'Wan Video 2.5 T2V',
  'Wan Video 2.5 I2V',
  'Wan Video 2.7',
  'MiniMax H3',
  'Hunyuan Video',
  'CogVideoX',
  'Mochi',
  // Audio and utility
  'ACE Audio',
  'Upscaler',
  'Other',
];
