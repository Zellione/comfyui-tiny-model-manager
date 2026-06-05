export type LinkKind =
  | { type: 'hf-resolve'; repo: string; revision: string; filename: string }
  | { type: 'hf-repo'; repo: string } // F-19 — future
  | { type: 'civitai-download'; versionId: number }
  | { type: 'civitai-model'; modelId: number } // F-20 — future
  | { type: 'unknown' }
  | { type: 'empty' };

const HF_RESOLVE_RE = /^https:\/\/huggingface\.co\/([\w.-]+\/[\w.-]+)\/resolve\/([\w.-]+)\/(.+)$/;
const HF_REPO_RE = /^https:\/\/huggingface\.co\/([\w.-]+\/[\w.-]+)\/?$/;
const CIVITAI_DL_RE = /^https:\/\/civitai\.com\/api\/download\/models\/(\d+)/;
const CIVITAI_MDL_RE = /^https:\/\/civitai\.com\/models\/(\d+)/;

export function detectLink(url: string): LinkKind {
  const s = url.trim();
  if (!s) return { type: 'empty' };

  const hfResolve = HF_RESOLVE_RE.exec(s);
  if (hfResolve)
    return {
      type: 'hf-resolve',
      repo: hfResolve[1],
      revision: hfResolve[2],
      filename: decodeURIComponent(hfResolve[3].split('?')[0]),
    };

  const hfRepo = HF_REPO_RE.exec(s);
  if (hfRepo) return { type: 'hf-repo', repo: hfRepo[1] };

  const civitaiDl = CIVITAI_DL_RE.exec(s);
  if (civitaiDl) return { type: 'civitai-download', versionId: +civitaiDl[1] };

  const civitaiMdl = CIVITAI_MDL_RE.exec(s);
  if (civitaiMdl) return { type: 'civitai-model', modelId: +civitaiMdl[1] };

  return { type: 'unknown' };
}
