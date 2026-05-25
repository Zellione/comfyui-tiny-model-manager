import folder_paths
import comfy.utils
import comfy_extras.chainner_models as model_loading


class TMMUpscaleModelLoader:
    CATEGORY = "tiny-model-manager"
    RETURN_TYPES = ("UPSCALE_MODEL",)
    RETURN_NAMES = ("upscale_model",)
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (folder_paths.get_filename_list("upscale_models"),),
            }
        }

    def load(self, model_name: str):
        model_path = folder_paths.get_full_path("upscale_models", model_name)
        sd = comfy.utils.load_torch_file(model_path, safe_load=True)
        out = model_loading.load_state_dict(sd).eval()
        return (out,)


NODE_CLASS_MAPPINGS = {
    "TMMUpscaleModelLoader": TMMUpscaleModelLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TMMUpscaleModelLoader": "Upscale Model Loader",
}
