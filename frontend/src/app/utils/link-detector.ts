export type LinkKind =
  | { type: 'hf-resolve'; repo: string; revision: string; filename: string; downloadUrl: string }
  | { type: 'hf-repo'; repo: string } // F-19 — future
  | { type: 'civitai-download'; versionId: number }
  | { type: 'civitai-model'; modelId: number } // F-20 — future
  | { type: 'unknown' }
  | { type: 'empty' };

// Both file-link shapes HuggingFace hands out are accepted: `/resolve/` streams the file,
// `/blob/` is the HTML file-viewer page the "copy link" button in the repo browser yields.
// The path group is greedy so files nested in subfolders (text_encoders/…) keep their prefix.
const HF_FILE_RE =
  /^https:\/\/huggingface\.co\/([\w.-]+\/[\w.-]+)\/(?:resolve|blob)\/([\w.-]+)\/(.+)$/;
const HF_REPO_RE = /^https:\/\/huggingface\.co\/([\w.-]+\/[\w.-]+)\/?$/;
// CivitAI serves the same site (identical model/version IDs) on civitai.com and its
// official alternate domain civitai.red; the backend allowlists both (url_guard.py).
const CIVITAI_DL_RE = /^https:\/\/civitai\.(?:com|red)\/api\/download\/models\/(\d+)/;
const CIVITAI_MDL_RE = /^https:\/\/civitai\.(?:com|red)\/models\/(\d+)/;

export function detectLink(url: string): LinkKind {
  const s = url.trim();
  if (!s) return { type: 'empty' };

  const hfFile = HF_FILE_RE.exec(s);
  if (hfFile) {
    const [, repo, revision, rawPath] = hfFile;
    // Keep the still-encoded path for the URL so percent-escaped names survive, and always
    // emit the `/resolve/` form — downloading a `/blob/` link stores the HTML viewer page.
    const path = rawPath.split('?')[0];
    return {
      type: 'hf-resolve',
      repo,
      revision,
      filename: decodeURIComponent(path),
      downloadUrl: `https://huggingface.co/${repo}/resolve/${revision}/${path}`,
    };
  }

  const hfRepo = HF_REPO_RE.exec(s);
  if (hfRepo) return { type: 'hf-repo', repo: hfRepo[1] };

  const civitaiDl = CIVITAI_DL_RE.exec(s);
  if (civitaiDl) return { type: 'civitai-download', versionId: +civitaiDl[1] };

  const civitaiMdl = CIVITAI_MDL_RE.exec(s);
  if (civitaiMdl) return { type: 'civitai-model', modelId: +civitaiMdl[1] };

  return { type: 'unknown' };
}
