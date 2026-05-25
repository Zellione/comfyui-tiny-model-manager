import folder_paths
import comfy.controlnet


class TMMControlNetLoader:
    CATEGORY = "tiny-model-manager"
    RETURN_TYPES = ("CONTROL_NET",)
    RETURN_NAMES = ("control_net",)
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "control_net_name": (folder_paths.get_filename_list("controlnet"),),
            }
        }

    def load(self, control_net_name: str):
        controlnet_path = folder_paths.get_full_path("controlnet", control_net_name)
        controlnet = comfy.controlnet.load_controlnet(controlnet_path)
        return (controlnet,)


NODE_CLASS_MAPPINGS = {
    "TMMControlNetLoader": TMMControlNetLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TMMControlNetLoader": "ControlNet Loader",
}
