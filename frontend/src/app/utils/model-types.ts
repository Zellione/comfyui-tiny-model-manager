/** The model-type folder names recognised across the dashboard and download views. */
export type ModelType =
  | 'checkpoints'
  | 'loras'
  | 'embeddings'
  | 'vae'
  | 'controlnet'
  | 'upscale_models'
  | 'hypernetworks'
  | 'clip_vision'
  | 'style_models'
  | 'gligen'
  | 'diffusion_models'
  | 'text_encoders'
  | 'photomaker'
  | 'vae_approx'
  | 'unet'
  | 'clip';

/** All model types in display order (matches the ModelType union above). */
export const MODEL_TYPES: ModelType[] = [
  'checkpoints',
  'loras',
  'embeddings',
  'vae',
  'controlnet',
  'upscale_models',
  'hypernetworks',
  'clip_vision',
  'style_models',
  'gligen',
  'diffusion_models',
  'text_encoders',
  'photomaker',
  'vae_approx',
  'unet',
  'clip',
];
