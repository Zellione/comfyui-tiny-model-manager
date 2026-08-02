"""Rebuild a ComfyUI workflow from a CivitAI image's generation metadata (F-130).

CivitAI re-encodes uploads to ``.jpeg`` on its CDN, so the ComfyUI graph embedded in the
original PNG is gone from the file. The API hands it over anyway: when the image was made
with ComfyUI, ``meta.comfy`` is a JSON *string* holding ``{"prompt": …, "workflow": …}``,
where ``workflow`` is a complete frontend graph. That is the exact path.

Everything else carries A1111-style parameters only, which are mapped onto a built-in
template graph. The template is SD-shaped (CheckpointLoaderSimple → KSampler → VAEDecode);
it is emitted for every base model, so callers should surface ``needs_template_warning()``
for anything outside the SD family — the graph will still load, but it will not run as-is.

Everything here is synchronous and pure, which makes it the main unit-test target.
"""

import json
import re

RECREATE_GRAPH = "graph"
RECREATE_PARAMS = "params"
RECREATE_NONE = ""

# Base models the template graph is actually shaped for. Anything else still gets a
# graph, but the caller is expected to warn that it will not run unmodified.
SD_FAMILY = frozenset(
    {
        "sd 1.4",
        "sd 1.5",
        "sd 1.5 lcm",
        "sd 1.5 hyper",
        "sd 2.0",
        "sd 2.1",
        "sdxl 0.9",
        "sdxl 1.0",
        "sdxl turbo",
        "sdxl lightning",
        "sdxl hyper",
        "pony",
        "illustrious",
        "noobai",
    }
)

# ``<lora:name:weight>`` — both quantifiers are bounded. An unbounded run next to an
# unanchored pattern is the non-linear-backtracking shape SonarQube flags as S8786.
_LORA_TAG_RE = re.compile(r"<lora:([^<>:]{1,120}):(-?\d{1,4}(?:\.\d{1,6})?)(?::[^<>]{0,40})?>")
_SIZE_RE = re.compile(r"(\d{1,5})\s*[x×]\s*(\d{1,5})")
_MODEL_EXT_RE = re.compile(r"\.(safetensors|ckpt|pt|pth|bin|sft)$", re.IGNORECASE)

# Metadata keys that on their own prove the image carries usable generation parameters.
_PARAM_KEYS = ("prompt", "Model", "hashes", "resources", "civitaiResources")

# A1111 sampler label -> (ComfyUI sampler_name, scheduler). The scheduler here is the
# default; a trailing " Karras"/" Exponential"/" SGM Uniform" on the label overrides it.
_SAMPLERS = {
    "euler": "euler",
    "euler a": "euler_ancestral",
    "euler ancestral": "euler_ancestral",
    "lms": "lms",
    "heun": "heun",
    "dpm2": "dpm_2",
    "dpm2 a": "dpm_2_ancestral",
    "dpm fast": "dpm_fast",
    "dpm adaptive": "dpm_adaptive",
    "dpm++ 2s a": "dpmpp_2s_ancestral",
    "dpm++ 2m": "dpmpp_2m",
    "dpm++ sde": "dpmpp_sde",
    "dpm++ 2m sde": "dpmpp_2m_sde",
    "dpm++ 3m sde": "dpmpp_3m_sde",
    "ddim": "ddim",
    "plms": "uni_pc",
    "unipc": "uni_pc",
    "uni pc": "uni_pc",
    "lcm": "lcm",
}
_SCHEDULER_SUFFIXES = (
    ("karras", "karras"),
    ("exponential", "exponential"),
    ("sgm uniform", "sgm_uniform"),
    ("sgm_uniform", "sgm_uniform"),
    ("simple", "simple"),
    ("beta", "beta"),
    ("ddim uniform", "ddim_uniform"),
)
_SCHEDULERS = frozenset(
    {"normal", "karras", "exponential", "sgm_uniform", "simple", "beta", "ddim_uniform"}
)

# Resource kinds of which a generation has at most one, so a nameless entry from one
# metadata source can safely be merged with a named entry from another.
_SINGLETON_KINDS = frozenset({"checkpoint", "vae"})


# --------------------------------------------------------------------------- classify


def is_comfy_graph(data: object) -> bool:
    """True for a ComfyUI frontend workflow graph.

    Real payloads carry ``nodes`` plus ``links``/``last_node_id``; requiring the node list
    alone is enough to reject readme JSON, package manifests and API-format prompts.

    This lives in the dependency-free module on purpose: ``workflow_store`` imports
    ``folder_paths`` from ComfyUI, and the predicate must stay importable without it.
    """
    return isinstance(data, dict) and isinstance(data.get("nodes"), list)


def graph_from_comfy(meta: dict | None) -> dict | None:
    """Return the embedded ComfyUI frontend graph, or ``None`` when there is none.

    ``meta["comfy"]`` is normally a JSON string; a pre-parsed dict is tolerated because
    that is cheaper for callers to construct in tests.
    """
    raw = (meta or {}).get("comfy")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    graph = raw.get("workflow")
    return graph if is_comfy_graph(graph) else None


def classify_meta(meta: dict | None) -> str:
    """Say which recreation path an image supports: graph, params, or neither."""
    if not isinstance(meta, dict) or not meta:
        return RECREATE_NONE
    if graph_from_comfy(meta) is not None:
        return RECREATE_GRAPH
    if any(meta.get(key) for key in _PARAM_KEYS):
        return RECREATE_PARAMS
    return RECREATE_NONE


def needs_template_warning(base_model: str) -> bool:
    """True when the SD-shaped template will not run as-is for this base model."""
    return (base_model or "").strip().lower() not in SD_FAMILY


# -------------------------------------------------------------------------- resources


def parse_lora_tags(prompt: str) -> list[tuple[str, float]]:
    """Extract ``<lora:name:weight>`` tags from a prompt."""
    found: list[tuple[str, float]] = []
    for name, weight in _LORA_TAG_RE.findall(prompt or ""):
        try:
            found.append((name.strip(), float(weight)))
        except ValueError:  # pragma: no cover - regex already constrains the shape
            continue
    return found


def _new_resource(kind: str, name: str = "", weight: float | None = None, **ids) -> dict:
    # ``weight`` stays None until a source actually states one. Defaulting it to 1.0 here
    # would let a weightless source (``hashes``) win the merge over the prompt tag that
    # carries the real strength.
    return {
        "kind": kind or "other",
        "name": name.strip(),
        "weight": weight,
        "model_version_id": str(ids.get("model_version_id") or ""),
        "hash": str(ids.get("hash") or "").lower(),
    }


def _identifies(existing: dict, item: dict) -> bool:
    """True when both entries clearly describe the same resource."""
    if existing["kind"] != item["kind"]:
        return False
    for key in ("model_version_id", "hash"):
        if existing[key] and item[key]:
            return existing[key] == item[key]
    if existing["name"] and item["name"]:
        return existing["name"].lower() == item["name"].lower()
    # Neither side shares an identifier the other has. For kinds that only ever occur
    # once per generation this still means "the same thing described twice" — which is
    # exactly how civitaiResources (version id, no name) and hashes (name, no version
    # id) each describe the single checkpoint.
    return existing["kind"] in _SINGLETON_KINDS


def _merge_into(entries: list[dict], item: dict) -> None:
    """Add ``item``, folding it into a matching entry so each resource appears once."""
    if not (item["name"] or item["model_version_id"] or item["hash"]):
        return
    for existing in entries:
        if not _identifies(existing, item):
            continue
        for key in ("name", "model_version_id", "hash"):
            if not existing[key] and item[key]:
                existing[key] = item[key]
        if existing["weight"] is None and item["weight"] is not None:
            existing["weight"] = item["weight"]
        return
    entries.append(item)


def _kind_of(raw: str) -> str:
    """Normalise the many spellings CivitAI uses for a resource kind.

    The legacy ``resources`` array calls the checkpoint ``"model"``, while
    ``civitaiResources`` calls it ``"checkpoint"`` — without folding those together the
    same checkpoint is reported twice.
    """
    kind = (raw or "").strip().lower()
    return {
        "model": "checkpoint",
        "lycoris": "lora",
        "locon": "lora",
        "textualinversion": "embedding",
        "embed": "embedding",
    }.get(kind, kind)


def _from_resource_lists(meta: dict, entries: list[dict]) -> None:
    """civitaiResources first — it is the only source carrying a modelVersionId."""
    for key in ("civitaiResources", "resources"):
        for raw in meta.get(key) or []:
            if not isinstance(raw, dict):
                continue
            _merge_into(
                entries,
                _new_resource(
                    _kind_of(raw.get("type", "")),
                    _basename(raw.get("modelName") or raw.get("name") or ""),
                    _opt_float(raw.get("weight")),
                    model_version_id=raw.get("modelVersionId"),
                    hash=raw.get("hash"),
                ),
            )


def _from_hashes(meta: dict, entries: list[dict]) -> None:
    """``hashes`` keys are ``model``/``vae``/``lora:<name>``; values are AutoV2 hashes."""
    hashes = meta.get("hashes")
    if not isinstance(hashes, dict):
        return
    for key, value in hashes.items():
        prefix, _, name = str(key).partition(":")
        kind = {"model": "checkpoint"}.get(prefix.lower(), _kind_of(prefix))
        _merge_into(entries, _new_resource(kind, name, hash=value))


def _from_plain_names(meta: dict, entries: list[dict]) -> None:
    for key, kind in (("Model", "checkpoint"), ("VAE", "vae")):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            _merge_into(entries, _new_resource(kind, _basename(value)))
    model_hash = meta.get("Model hash")
    if isinstance(model_hash, str) and model_hash.strip():
        _merge_into(entries, _new_resource("checkpoint", "", hash=model_hash))


def _from_prompt(meta: dict, entries: list[dict]) -> None:
    for name, weight in parse_lora_tags(meta.get("prompt", "")):
        _merge_into(entries, _new_resource("lora", name, weight))


def referenced_resources(meta: dict | None) -> list[dict]:
    """Every model the image references, normalised and de-duplicated.

    Sources are consulted best-first: ``civitaiResources`` (carries a modelVersionId),
    then ``resources``, then ``hashes`` (names + AutoV2), then the bare ``Model``/``VAE``
    strings, then ``<lora:…>`` tags in the prompt.
    """
    if not isinstance(meta, dict):
        return []
    entries: list[dict] = []
    _from_resource_lists(meta, entries)
    _from_hashes(meta, entries)
    _from_plain_names(meta, entries)
    _from_prompt(meta, entries)
    for entry in entries:
        if entry["weight"] is None:
            entry["weight"] = 1.0
    return entries


# --------------------------------------------------------------------------- template


def _as_float(value: object, default: float) -> float:
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _opt_float(value: object) -> float | None:
    """Float, or None when the source did not state a value at all."""
    if value is None:
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _as_int(value: object, default: int) -> int:
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def _basename(value: str) -> str:
    """Last path segment of a model reference, tolerating Windows separators."""
    return value.replace("\\", "/").rsplit("/", 1)[-1].strip()


def _model_filename(name: str) -> str:
    """Best-effort ComfyUI widget value for a model reference."""
    cleaned = _basename(name)
    if not cleaned:
        return ""
    return cleaned if _MODEL_EXT_RE.search(cleaned) else f"{cleaned}.safetensors"


def _dimensions(meta: dict) -> tuple[int, int]:
    width = _as_int(meta.get("width"), 0)
    height = _as_int(meta.get("height"), 0)
    if width and height:
        return width, height
    match = _SIZE_RE.search(str(meta.get("Size") or ""))
    if match:
        return int(match.group(1)), int(match.group(2))
    return 512, 512


def _sampler_and_scheduler(meta: dict) -> tuple[str, str]:
    label = str(meta.get("sampler") or "").strip().lower()
    scheduler = ""
    for suffix, mapped in _SCHEDULER_SUFFIXES:
        if label.endswith(f" {suffix}"):
            label = label[: -len(suffix) - 1].strip()
            scheduler = mapped
            break
    explicit = str(meta.get("scheduler") or "").strip().lower().replace(" ", "_")
    if explicit in _SCHEDULERS:
        scheduler = explicit
    return _SAMPLERS.get(label, "euler"), scheduler or "normal"


class _GraphBuilder:
    """Assembles a ComfyUI *frontend* graph (nodes + links), not an API prompt.

    ``app.loadGraphData()`` and :func:`workflow_store.is_comfy_graph` both expect this
    form, so the template must not emit the API/prompt format.
    """

    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.links: list[list] = []
        self._node_id = 0
        self._link_id = 0

    def add(self, node_type: str, widgets: list, inputs: list, outputs: list, pos: list) -> dict:
        self._node_id += 1
        node = {
            "id": self._node_id,
            "type": node_type,
            "pos": pos,
            "size": [300, 120],
            "flags": {},
            "order": len(self.nodes),
            "mode": 0,
            "inputs": [{"name": n, "type": t, "link": None} for n, t in inputs],
            "outputs": [
                {"name": n, "type": t, "links": [], "slot_index": i}
                for i, (n, t) in enumerate(outputs)
            ],
            "properties": {"Node name for S&R": node_type},
            "widgets_values": widgets,
        }
        self.nodes.append(node)
        return node

    def connect(self, src: dict, src_slot: int, dst: dict, dst_slot: int) -> None:
        self._link_id += 1
        link_type = src["outputs"][src_slot]["type"]
        self.links.append([self._link_id, src["id"], src_slot, dst["id"], dst_slot, link_type])
        src["outputs"][src_slot]["links"].append(self._link_id)
        dst["inputs"][dst_slot]["link"] = self._link_id

    def finish(self) -> dict:
        return {
            "last_node_id": self._node_id,
            "last_link_id": self._link_id,
            "nodes": self.nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4,
        }


def _checkpoint_name(meta: dict, filenames: dict[str, str]) -> str:
    for resource in referenced_resources(meta):
        if resource["kind"] == "checkpoint":
            local = filenames.get(resource["name"].lower())
            return local or _model_filename(resource["name"])
    return _model_filename(str(meta.get("Model") or ""))


def _lora_chain(
    builder: _GraphBuilder, meta: dict, filenames: dict[str, str], source: dict
) -> dict:
    """Chain one LoraLoader per referenced LoRA; returns the final MODEL/CLIP node."""
    current = source
    x = 340
    for resource in referenced_resources(meta):
        if resource["kind"] != "lora":
            continue
        local = filenames.get(resource["name"].lower())
        weight = resource["weight"]
        node = builder.add(
            "LoraLoader",
            [local or _model_filename(resource["name"]), weight, weight],
            [("model", "MODEL"), ("clip", "CLIP")],
            [("MODEL", "MODEL"), ("CLIP", "CLIP")],
            [x, 60],
        )
        builder.connect(current, 0, node, 0)
        builder.connect(current, 1, node, 1)
        current = node
        x += 320
    return current


def build_template_graph(meta: dict | None, filenames: dict[str, str] | None = None) -> dict:
    """Map A1111-style generation parameters onto an SD-shaped txt2img graph.

    ``filenames`` optionally maps a lowercased resource name to the filename it is
    installed under locally, so a recreated graph points at real files when the models
    are already in the library.
    """
    meta = meta if isinstance(meta, dict) else {}
    filenames = filenames or {}
    width, height = _dimensions(meta)
    sampler, scheduler = _sampler_and_scheduler(meta)
    builder = _GraphBuilder()

    checkpoint = builder.add(
        "CheckpointLoaderSimple",
        [_checkpoint_name(meta, filenames)],
        [],
        [("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        [20, 60],
    )
    tail = _lora_chain(builder, meta, filenames, checkpoint)

    positive = builder.add(
        "CLIPTextEncode",
        [str(meta.get("prompt") or "")],
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        [700, 60],
    )
    negative = builder.add(
        "CLIPTextEncode",
        [str(meta.get("negativePrompt") or "")],
        [("clip", "CLIP")],
        [("CONDITIONING", "CONDITIONING")],
        [700, 280],
    )
    latent = builder.add(
        "EmptyLatentImage", [width, height, 1], [], [("LATENT", "LATENT")], [700, 500]
    )
    sampler_node = builder.add(
        "KSampler",
        [
            _as_int(meta.get("seed"), 0),
            "randomize",
            _as_int(meta.get("steps"), 20),
            _as_float(meta.get("cfgScale"), 7.0),
            sampler,
            scheduler,
            _as_float(meta.get("denoise"), 1.0),
        ],
        [
            ("model", "MODEL"),
            ("positive", "CONDITIONING"),
            ("negative", "CONDITIONING"),
            ("latent_image", "LATENT"),
        ],
        [("LATENT", "LATENT")],
        [1060, 60],
    )
    decode = builder.add(
        "VAEDecode",
        [],
        [("samples", "LATENT"), ("vae", "VAE")],
        [("IMAGE", "IMAGE")],
        [1400, 60],
    )
    save = builder.add("SaveImage", ["ComfyUI"], [("images", "IMAGE")], [], [1700, 60])

    builder.connect(tail, 1, positive, 0)
    builder.connect(tail, 1, negative, 0)
    builder.connect(tail, 0, sampler_node, 0)
    builder.connect(positive, 0, sampler_node, 1)
    builder.connect(negative, 0, sampler_node, 2)
    builder.connect(latent, 0, sampler_node, 3)
    builder.connect(sampler_node, 0, decode, 0)
    builder.connect(checkpoint, 2, decode, 1)
    builder.connect(decode, 0, save, 0)
    return builder.finish()
