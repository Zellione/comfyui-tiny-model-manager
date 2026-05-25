import os
import folder_paths


class TMMEmbeddingHelper:
    CATEGORY = "tiny-model-manager"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("embedding_ref",)
    FUNCTION = "get"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "embedding_name": (folder_paths.get_filename_list("embeddings"),),
            }
        }

    def get(self, embedding_name: str):
        stem = os.path.splitext(embedding_name)[0]
        return (f"embedding:{stem}",)


NODE_CLASS_MAPPINGS = {
    "TMMEmbeddingHelper": TMMEmbeddingHelper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TMMEmbeddingHelper": "Embedding Helper",
}
