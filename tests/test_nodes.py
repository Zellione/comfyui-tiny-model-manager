"""Tests for ComfyUI workflow nodes (py/nodes/*.py).

ComfyUI stubs (folder_paths, comfy.*) are installed by conftest.py before
these modules are imported.
"""

import pytest

# ---------------------------------------------------------------------------
# NODE_CLASS_MAPPINGS / NODE_DISPLAY_NAME_MAPPINGS exports
# ---------------------------------------------------------------------------


class TestNodeExports:
    def test_lora_loader_exports(self):
        from py.nodes.lora_loader_with_triggers import (
            NODE_CLASS_MAPPINGS,
            NODE_DISPLAY_NAME_MAPPINGS,
        )

        assert "TMMLoraLoader" in NODE_CLASS_MAPPINGS
        assert "TMMLoraLoader" in NODE_DISPLAY_NAME_MAPPINGS

    def test_checkpoint_loader_exports(self):
        from py.nodes.checkpoint_loader_with_triggers import (
            NODE_CLASS_MAPPINGS,
            NODE_DISPLAY_NAME_MAPPINGS,
        )

        assert "TMMCheckpointLoader" in NODE_CLASS_MAPPINGS
        assert "TMMCheckpointLoader" in NODE_DISPLAY_NAME_MAPPINGS

    def test_vae_loader_exports(self):
        from py.nodes.vae_loader_with_triggers import (
            NODE_CLASS_MAPPINGS,
        )

        assert "TMMVaeLoader" in NODE_CLASS_MAPPINGS

    def test_controlnet_loader_exports(self):
        from py.nodes.controlnet_loader_with_triggers import (
            NODE_CLASS_MAPPINGS,
        )

        assert "TMMControlNetLoader" in NODE_CLASS_MAPPINGS

    def test_embedding_helper_exports(self):
        from py.nodes.embedding_helper import (
            NODE_CLASS_MAPPINGS,
            NODE_DISPLAY_NAME_MAPPINGS,
        )

        assert "TMMEmbeddingHelper" in NODE_CLASS_MAPPINGS
        assert NODE_DISPLAY_NAME_MAPPINGS["TMMEmbeddingHelper"] == "Embedding Helper"

    def test_upscale_model_loader_exports(self):
        from py.nodes.upscale_model_loader import (
            NODE_CLASS_MAPPINGS,
        )

        assert "TMMUpscaleModelLoader" in NODE_CLASS_MAPPINGS


# ---------------------------------------------------------------------------
# INPUT_TYPES structure
# ---------------------------------------------------------------------------


class TestInputTypes:
    def test_lora_loader_input_types_shape(self):
        from py.nodes.lora_loader_with_triggers import TMMLoraLoader

        it = TMMLoraLoader.INPUT_TYPES()
        assert "required" in it
        req = it["required"]
        assert "model" in req
        assert "clip" in req
        assert "lora_name" in req
        assert "strength_model" in req
        assert "strength_clip" in req

    def test_checkpoint_loader_input_types(self):
        from py.nodes.checkpoint_loader_with_triggers import TMMCheckpointLoader

        it = TMMCheckpointLoader.INPUT_TYPES()
        assert "ckpt_name" in it["required"]

    def test_embedding_helper_input_types(self):
        from py.nodes.embedding_helper import TMMEmbeddingHelper

        it = TMMEmbeddingHelper.INPUT_TYPES()
        assert "embedding_name" in it["required"]

    def test_lora_loader_return_types(self):
        from py.nodes.lora_loader_with_triggers import TMMLoraLoader

        assert "STRING" in TMMLoraLoader.RETURN_TYPES
        assert "trigger_words" in TMMLoraLoader.RETURN_NAMES


# ---------------------------------------------------------------------------
# EmbeddingHelper.get — pure string formatting
# ---------------------------------------------------------------------------


class TestEmbeddingHelper:
    def test_get_returns_embedding_prefix(self):
        from py.nodes.embedding_helper import TMMEmbeddingHelper

        node = TMMEmbeddingHelper()
        result = node.get("my_embedding.pt")
        assert result == ("embedding:my_embedding",)

    def test_get_strips_extension(self):
        from py.nodes.embedding_helper import TMMEmbeddingHelper

        node = TMMEmbeddingHelper()
        (ref,) = node.get("cool.safetensors")
        assert ref == "embedding:cool"

    def test_get_with_no_extension(self):
        from py.nodes.embedding_helper import TMMEmbeddingHelper

        node = TMMEmbeddingHelper()
        (ref,) = node.get("noext")
        assert ref == "embedding:noext"


# ---------------------------------------------------------------------------
# CATEGORY assignment
# ---------------------------------------------------------------------------


class TestNodeCategory:
    @pytest.mark.parametrize(
        "module,cls",
        [
            ("py.nodes.lora_loader_with_triggers", "TMMLoraLoader"),
            ("py.nodes.checkpoint_loader_with_triggers", "TMMCheckpointLoader"),
            ("py.nodes.embedding_helper", "TMMEmbeddingHelper"),
            ("py.nodes.vae_loader_with_triggers", "TMMVaeLoader"),
            ("py.nodes.controlnet_loader_with_triggers", "TMMControlNetLoader"),
            ("py.nodes.upscale_model_loader", "TMMUpscaleModelLoader"),
        ],
    )
    def test_category_is_tiny_model_manager(self, module, cls):
        import importlib

        mod = importlib.import_module(module)
        node_cls = getattr(mod, cls)
        assert node_cls.CATEGORY == "tiny-model-manager"
