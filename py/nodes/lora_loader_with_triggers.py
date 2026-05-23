import asyncio
import folder_paths
import comfy.utils
import comfy.sd


def _get_trigger_words_sync(filename: str) -> str:
    """Fetch trigger words from DB synchronously (runs a coroutine in the event loop)."""
    try:
        from ..db import model_repo

        async def _fetch():
            meta = await model_repo.get_model_by_filename(filename)
            if meta:
                return ", ".join(meta.get("trigger_words", []))
            return ""

        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule it and return empty — the node isn't async-capable
            future = asyncio.ensure_future(_fetch())
            # Best-effort: return empty string if not immediately available
            return ""
        return loop.run_until_complete(_fetch())
    except Exception:
        return ""


class LoraLoaderWithTriggers:
    CATEGORY = "tiny-model-manager"
    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("model", "clip", "trigger_words")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_name": (folder_paths.get_filename_list("loras"),),
                "strength_model": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_clip": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
            }
        }

    def load(self, model, clip, lora_name: str, strength_model: float, strength_clip: float):
        lora_path = folder_paths.get_full_path("loras", lora_name)
        lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
        model_out, clip_out = comfy.sd.load_lora_for_models(model, clip, lora, strength_model, strength_clip)
        trigger_words = _get_trigger_words_sync(lora_name)
        return (model_out, clip_out, trigger_words)


NODE_CLASS_MAPPINGS = {
    "LoraLoaderWithTriggers": LoraLoaderWithTriggers,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraLoaderWithTriggers": "LoRA Loader (with Trigger Words)",
}
