import comfy.sd
import folder_paths


class TMMVaeLoader:
    CATEGORY = "tiny-model-manager"
    RETURN_TYPES = ("VAE",)
    RETURN_NAMES = ("vae",)
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "vae_name": (folder_paths.get_filename_list("vae"),),
            }
        }

    def load(self, vae_name: str):
        vae_path = folder_paths.get_full_path("vae", vae_name)
        vae = comfy.sd.VAE(ckpt_path=vae_path)
        return (vae,)


NODE_CLASS_MAPPINGS = {
    "TMMVaeLoader": TMMVaeLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TMMVaeLoader": "VAE Loader",
}
