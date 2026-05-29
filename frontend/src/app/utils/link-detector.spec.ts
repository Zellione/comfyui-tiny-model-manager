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
    });
  });

  it('strips query string from HF resolve filename', () => {
    const result = detectLink(
      'https://huggingface.co/user/repo/resolve/main/model.safetensors?download=true',
    );
    if (result.type !== 'hf-resolve') throw new Error('wrong type');
    expect(result.filename).toBe('model.safetensors');
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
