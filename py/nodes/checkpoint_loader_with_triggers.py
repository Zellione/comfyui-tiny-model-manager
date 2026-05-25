import folder_paths
import comfy.sd


class TMMCheckpointLoader:
    CATEGORY = "tiny-model-manager"
    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    RETURN_NAMES = ("model", "clip", "vae")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ckpt_name": (folder_paths.get_filename_list("checkpoints"),),
            }
        }

    def load(self, ckpt_name: str):
        ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
        out = comfy.sd.load_checkpoint_guess_config(
            ckpt_path,
            output_vae=True,
            output_clip=True,
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
        )
        return (out[0], out[1], out[2])


NODE_CLASS_MAPPINGS = {
    "TMMCheckpointLoader": TMMCheckpointLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TMMCheckpointLoader": "Checkpoint Loader",
}
