import folder_paths
import comfy.utils
import comfy.sd
from ._utils import get_trigger_words_sync


class TMMLoraLoader:
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
        trigger_words = get_trigger_words_sync(lora_name)
        return (model_out, clip_out, trigger_words)


NODE_CLASS_MAPPINGS = {
    "TMMLoraLoader": TMMLoraLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TMMLoraLoader": "LoRA Loader (with Trigger Words)",
}
