import { detectLink } from './link-detector';

describe('detectLink', () => {
  it('returns empty for blank input', () => {
    expect(detectLink('')).toEqual({ type: 'empty' });
    expect(detectLink('   ')).toEqual({ type: 'empty' });
  });

  it('detects HuggingFace resolve URL', () => {
    const result = detectLink('https://huggingface.co/user/repo/resolve/main/model.safetensors');
    expect(result).toEqual({
      type: 'hf-resolve',
      repo: 'user/repo',
      revision: 'main',
      filename: 'model.safetensors',
      downloadUrl: 'https://huggingface.co/user/repo/resolve/main/model.safetensors',
    });
  });

  it('strips query string from HF resolve filename and download URL', () => {
    const result = detectLink(
      'https://huggingface.co/user/repo/resolve/main/model.safetensors?download=true',
    );
    if (result.type !== 'hf-resolve') throw new Error('wrong type');
    expect(result.filename).toBe('model.safetensors');
    expect(result.downloadUrl).toBe(
      'https://huggingface.co/user/repo/resolve/main/model.safetensors',
    );
  });

  it('detects HuggingFace blob URL and rewrites it to a resolve download URL', () => {
    const result = detectLink('https://huggingface.co/user/repo/blob/main/model.safetensors');
    expect(result).toEqual({
      type: 'hf-resolve',
      repo: 'user/repo',
      revision: 'main',
      filename: 'model.safetensors',
      downloadUrl: 'https://huggingface.co/user/repo/resolve/main/model.safetensors',
    });
  });

  it('keeps the subfolder prefix of a nested blob URL', () => {
    const result = detectLink(
      'https://huggingface.co/Comfy-Org/Qwen3-VL/blob/main/text_encoders/qwen3vl_4b_bf16.safetensors',
    );
    expect(result).toEqual({
      type: 'hf-resolve',
      repo: 'Comfy-Org/Qwen3-VL',
      revision: 'main',
      filename: 'text_encoders/qwen3vl_4b_bf16.safetensors',
      downloadUrl:
        'https://huggingface.co/Comfy-Org/Qwen3-VL/resolve/main/text_encoders/qwen3vl_4b_bf16.safetensors',
    });
  });

  it('leaves the percent-encoding of a file path intact in the download URL', () => {
    const result = detectLink('https://huggingface.co/user/repo/blob/main/my%20model.safetensors');
    if (result.type !== 'hf-resolve') throw new Error('wrong type');
    expect(result.filename).toBe('my model.safetensors');
    expect(result.downloadUrl).toBe(
      'https://huggingface.co/user/repo/resolve/main/my%20model.safetensors',
    );
  });

  it('detects HuggingFace repo URL', () => {
    const result = detectLink('https://huggingface.co/user/repo');
    expect(result).toEqual({ type: 'hf-repo', repo: 'user/repo' });
  });

  it('detects CivitAI direct download URL', () => {
    const result = detectLink('https://civitai.com/api/download/models/12345');
    expect(result).toEqual({ type: 'civitai-download', versionId: 12345 });
  });

  it('detects CivitAI model page URL', () => {
    const result = detectLink('https://civitai.com/models/67890?tab=versions');
    expect(result).toEqual({ type: 'civitai-model', modelId: 67890 });
  });

  it('detects CivitAI direct download URL on the civitai.red domain', () => {
    const result = detectLink('https://civitai.red/api/download/models/12345');
    expect(result).toEqual({ type: 'civitai-download', versionId: 12345 });
  });

  it('detects CivitAI model page URL on the civitai.red domain', () => {
    const result = detectLink(
      'https://civitai.red/models/2237711/z-image-turbo?modelVersionId=3225140',
    );
    expect(result).toEqual({ type: 'civitai-model', modelId: 2237711 });
  });

  it('returns unknown for unrecognised URL', () => {
    expect(detectLink('https://example.com/some-model.safetensors')).toEqual({
      type: 'unknown',
    });
  });

  it('trims surrounding whitespace before matching', () => {
    const result = detectLink('  https://huggingface.co/user/repo  ');
    expect(result).toEqual({ type: 'hf-repo', repo: 'user/repo' });
  });
});
