export type LinkKind =
  | { type: 'hf-resolve'; repo: string; revision: string; filename: string }
  | { type: 'hf-repo'; repo: string }           // F-19 — future
  | { type: 'civitai-download'; versionId: number }
  | { type: 'civitai-model'; modelId: number }  // F-20 — future
  | { type: 'unknown' }
  | { type: 'empty' };

const HF_RESOLVE_RE  = /^https:\/\/huggingface\.co\/([\w.\-]+\/[\w.\-]+)\/resolve\/([\w.\-]+)\/(.+)$/;
const HF_REPO_RE     = /^https:\/\/huggingface\.co\/([\w.\-]+\/[\w.\-]+)\/?$/;
const CIVITAI_DL_RE  = /^https:\/\/civitai\.com\/api\/download\/models\/(\d+)/;
const CIVITAI_MDL_RE = /^https:\/\/civitai\.com\/models\/(\d+)/;

export function detectLink(url: string): LinkKind {
  const s = url.trim();
  if (!s) return { type: 'empty' };
  let m: RegExpMatchArray | null;
  if ((m = s.match(HF_RESOLVE_RE)))  return { type: 'hf-resolve', repo: m[1], revision: m[2], filename: decodeURIComponent(m[3].split('?')[0]) };
  if ((m = s.match(HF_REPO_RE)))     return { type: 'hf-repo', repo: m[1] };
  if ((m = s.match(CIVITAI_DL_RE)))  return { type: 'civitai-download', versionId: +m[1] };
  if ((m = s.match(CIVITAI_MDL_RE))) return { type: 'civitai-model', modelId: +m[1] };
  return { type: 'unknown' };
}
