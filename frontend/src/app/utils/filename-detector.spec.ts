import { describe, expect, it } from 'vitest';
import { detectFromFilename, FilenameKeyword } from './filename-detector';

const kw = (
  keyword: string,
  base_model: string | null,
  model_type: string | null,
  id = 1,
): FilenameKeyword => ({ id, keyword, base_model, model_type, sort_order: id * 10 });

describe('detectFromFilename', () => {
  it('returns empty detection for an empty keyword list', () => {
    const result = detectFromFilename('model.safetensors', []);
    expect(result.baseModel).toBe('');
    expect(result.modelType).toBeNull();
  });

  it('returns empty detection when no keyword matches', () => {
    const result = detectFromFilename('model.safetensors', [kw('sdxl', 'SDXL 1.0', null)]);
    expect(result.baseModel).toBe('');
    expect(result.modelType).toBeNull();
  });

  it('sets baseModel when matching keyword has base_model', () => {
    const result = detectFromFilename('sdxl_model.safetensors', [kw('sdxl', 'SDXL 1.0', null)]);
    expect(result.baseModel).toBe('SDXL 1.0');
    expect(result.modelType).toBeNull();
  });

  it('sets modelType when matching keyword has model_type', () => {
    const result = detectFromFilename('my_lora.safetensors', [kw('lora', null, 'loras')]);
    expect(result.baseModel).toBe('');
    expect(result.modelType).toBe('loras');
  });

  it('sets both baseModel and modelType from a single matching keyword', () => {
    const result = detectFromFilename('sdxl_model.safetensors', [
      kw('sdxl', 'SDXL 1.0', 'checkpoints'),
    ]);
    expect(result.baseModel).toBe('SDXL 1.0');
    expect(result.modelType).toBe('checkpoints');
  });

  it('first matching keyword wins for baseModel', () => {
    const result = detectFromFilename('sdxl_flux_model.safetensors', [
      kw('sdxl', 'SDXL 1.0', null, 1),
      kw('flux', 'Flux.1 D', null, 2),
    ]);
    expect(result.baseModel).toBe('SDXL 1.0');
  });

  it('first matching keyword wins for modelType', () => {
    const result = detectFromFilename('lora_embed.safetensors', [
      kw('lora', null, 'loras', 1),
      kw('embed', null, 'embeddings', 2),
    ]);
    expect(result.modelType).toBe('loras');
  });

  it('breaks early once both baseModel and modelType are resolved', () => {
    const keywords: FilenameKeyword[] = [
      kw('sdxl', 'SDXL 1.0', 'checkpoints', 1),
      {
        id: 2,
        keyword: 'lora',
        base_model: 'ShouldNotAppear',
        model_type: 'loras',
        sort_order: 20,
      },
    ];
    const result = detectFromFilename('sdxl_lora.safetensors', keywords);
    expect(result.baseModel).toBe('SDXL 1.0');
    expect(result.modelType).toBe('checkpoints');
  });

  it('skips keyword with null base_model without overwriting previously found baseModel', () => {
    const result = detectFromFilename('sdxl_lora.safetensors', [
      kw('lora', null, 'loras', 1),
      kw('sdxl', 'SDXL 1.0', null, 2),
    ]);
    expect(result.baseModel).toBe('SDXL 1.0');
    expect(result.modelType).toBe('loras');
  });

  it('matching is case-insensitive', () => {
    const result = detectFromFilename('SDXL_Model.safetensors', [kw('sdxl', 'SDXL 1.0', null)]);
    expect(result.baseModel).toBe('SDXL 1.0');
  });
});
