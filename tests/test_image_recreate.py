"""Unit tests for rebuilding a workflow from CivitAI image metadata (F-130).

The shapes exercised here were captured from live ``/api/v1/images`` responses, including
the quirks that are easy to get wrong: ``meta.comfy`` is a JSON *string*, the legacy
``resources`` array calls the checkpoint ``"model"`` while ``civitaiResources`` calls it
``"checkpoint"``, and ``hashes`` values are AutoV2 rather than full SHA-256.
"""

import json

import pytest

from py.services import image_recreate as ir

EMBEDDED_GRAPH = {
    "last_node_id": 3,
    "nodes": [{"id": 1, "type": "KSampler"}, {"id": 2, "type": "SaveImage"}],
    "links": [],
}

A1111_META = {
    "seed": 657597278555149,
    "Model": "Krea\\krea2_turbo_fp8_scaled.safetensors",
    "steps": 8,
    "width": 832,
    "height": 1248,
    "cfgScale": 3.5,
    "sampler": "DPM++ 2M Karras",
    "prompt": "a robot dog <lora:Detailer:0.8> <lora:Sunset:0.55>",
    "negativePrompt": "blurry",
    "hashes": {
        "model": "eb4dd8c612",
        "lora:Detailer": "5ec8728156",
        "lora:Sunset": "194abdd531",
    },
}


def _nodes_by_type(graph, node_type):
    return [n for n in graph["nodes"] if n["type"] == node_type]


class TestClassifyMeta:
    def test_comfy_json_string_is_a_graph(self):
        meta = {"comfy": json.dumps({"prompt": {}, "workflow": EMBEDDED_GRAPH})}
        assert ir.classify_meta(meta) == ir.RECREATE_GRAPH
        assert ir.graph_from_comfy(meta) == EMBEDDED_GRAPH

    def test_comfy_already_parsed_dict_is_accepted(self):
        meta = {"comfy": {"workflow": EMBEDDED_GRAPH}}
        assert ir.graph_from_comfy(meta) == EMBEDDED_GRAPH

    def test_malformed_comfy_json_falls_back_to_params(self):
        meta = {"comfy": "{not json", "prompt": "cat"}
        assert ir.graph_from_comfy(meta) is None
        assert ir.classify_meta(meta) == ir.RECREATE_PARAMS

    def test_comfy_without_a_workflow_key_is_not_a_graph(self):
        # The API prompt format alone is not loadable by the ComfyUI frontend.
        meta = {"comfy": json.dumps({"prompt": {"1": {"class_type": "KSampler"}}})}
        assert ir.graph_from_comfy(meta) is None

    def test_params_only(self):
        assert ir.classify_meta(A1111_META) == ir.RECREATE_PARAMS

    @pytest.mark.parametrize("meta", [None, {}, {"Size": "512x512"}])
    def test_no_usable_metadata(self, meta):
        assert ir.classify_meta(meta) == ir.RECREATE_NONE

    @pytest.mark.parametrize("key", ["prompt", "Model", "hashes", "resources"])
    def test_any_single_param_key_is_enough(self, key):
        assert ir.classify_meta({key: "x"}) == ir.RECREATE_PARAMS


class TestTemplateWarning:
    @pytest.mark.parametrize("base", ["SD 1.5", "SDXL 1.0", "pony", "Illustrious"])
    def test_sd_family_needs_no_warning(self, base):
        assert ir.needs_template_warning(base) is False

    @pytest.mark.parametrize("base", ["Flux.1 D", "Krea 2", "Qwen", ""])
    def test_everything_else_warns(self, base):
        assert ir.needs_template_warning(base) is True


class TestParseLoraTags:
    def test_extracts_name_and_weight(self):
        assert ir.parse_lora_tags("x <lora:Foo:0.8> y <lora:Bar:1>") == [("Foo", 0.8), ("Bar", 1.0)]

    def test_tolerates_a_second_weight(self):
        assert ir.parse_lora_tags("<lora:Foo:0.8:0.5>") == [("Foo", 0.8)]

    def test_negative_weight(self):
        assert ir.parse_lora_tags("<lora:Foo:-0.4>") == [("Foo", -0.4)]

    def test_long_run_does_not_match_past_the_bound(self):
        # The quantifiers are bounded to keep the pattern linear (SonarQube S8786); a name
        # longer than the bound must simply not match rather than backtracking.
        assert ir.parse_lora_tags(f"<lora:{'a' * 200}:1>") == []

    @pytest.mark.parametrize("text", ["", "no tags here", "<lora:broken>"])
    def test_no_matches(self, text):
        assert ir.parse_lora_tags(text) == []


class TestReferencedResources:
    def test_merges_hashes_and_prompt_weights(self):
        resources = ir.referenced_resources(A1111_META)
        by_name = {r["name"]: r for r in resources}
        assert by_name["Detailer"]["kind"] == "lora"
        assert by_name["Detailer"]["weight"] == 0.8
        assert by_name["Detailer"]["hash"] == "5ec8728156"
        # The Model string and the hashes "model" key describe one checkpoint, not two.
        checkpoints = [r for r in resources if r["kind"] == "checkpoint"]
        assert checkpoints == [
            {
                "kind": "checkpoint",
                "name": "krea2_turbo_fp8_scaled.safetensors",
                "weight": 1.0,
                "model_version_id": "",
                "hash": "eb4dd8c612",
            }
        ]

    def test_legacy_model_type_folds_into_checkpoint(self):
        # `resources` says "model", `civitaiResources` says "checkpoint" — same thing.
        meta = {
            "resources": [{"type": "model", "name": "epic.safetensors", "hash": "abc1234567"}],
            "civitaiResources": [{"type": "checkpoint", "modelVersionId": 99}],
        }
        resources = ir.referenced_resources(meta)
        assert len(resources) == 1
        assert resources[0]["kind"] == "checkpoint"
        assert resources[0]["name"] == "epic.safetensors"
        assert resources[0]["model_version_id"] == "99"

    def test_civitai_resources_supply_the_version_id(self):
        meta = {"civitaiResources": [{"type": "lora", "modelVersionId": 42, "weight": 0.7}]}
        assert ir.referenced_resources(meta) == [
            {"kind": "lora", "name": "", "weight": 0.7, "model_version_id": "42", "hash": ""}
        ]

    def test_names_are_basenamed(self):
        meta = {"resources": [{"type": "lora", "name": "sub\\dir\\thing.safetensors"}]}
        assert ir.referenced_resources(meta)[0]["name"] == "thing.safetensors"

    def test_lycoris_and_textual_inversion_are_normalised(self):
        meta = {
            "resources": [
                {"type": "lycoris", "name": "a", "hash": "1111111111"},
                {"type": "TextualInversion", "name": "b", "hash": "2222222222"},
            ]
        }
        kinds = [r["kind"] for r in ir.referenced_resources(meta)]
        assert kinds == ["lora", "embedding"]

    def test_vae_is_reported_separately(self):
        meta = {"VAE": "sdxl_vae.safetensors", "Model": "base.safetensors"}
        kinds = {r["kind"] for r in ir.referenced_resources(meta)}
        assert kinds == {"vae", "checkpoint"}

    def test_bare_model_hash_merges_into_the_named_checkpoint(self):
        meta = {"Model": "base.safetensors", "Model hash": "DEADBEEF00"}
        resources = ir.referenced_resources(meta)
        assert len(resources) == 1
        assert resources[0]["hash"] == "deadbeef00"

    def test_entries_without_any_identifier_are_dropped(self):
        assert ir.referenced_resources({"resources": [{"type": "lora"}, "notadict"]}) == []

    @pytest.mark.parametrize("meta", [None, {}, "nonsense"])
    def test_unusable_meta_yields_nothing(self, meta):
        assert ir.referenced_resources(meta) == []


class TestBuildTemplateGraph:
    def test_emits_the_frontend_graph_format(self):
        graph = ir.build_template_graph(A1111_META)
        # Not the API/prompt format: loadGraphData and is_comfy_graph both want this one.
        assert ir.is_comfy_graph(graph)
        assert set(graph) >= {"nodes", "links", "last_node_id", "last_link_id"}

    def test_wires_the_full_pipeline(self):
        graph = ir.build_template_graph(A1111_META)
        types = [n["type"] for n in graph["nodes"]]
        assert types[0] == "CheckpointLoaderSimple"
        assert types[-1] == "SaveImage"
        assert types.count("LoraLoader") == 2
        assert types.count("CLIPTextEncode") == 2
        # Every declared input is connected.
        assert all(i["link"] is not None for n in graph["nodes"] for i in n["inputs"])

    def test_lora_chain_threads_model_and_clip(self):
        graph = ir.build_template_graph(A1111_META)
        loras = _nodes_by_type(graph, "LoraLoader")
        checkpoint = _nodes_by_type(graph, "CheckpointLoaderSimple")[0]
        first_model_link = loras[0]["inputs"][0]["link"]
        assert first_model_link in checkpoint["outputs"][0]["links"]
        # Second LoRA takes its model from the first, not from the checkpoint.
        assert loras[1]["inputs"][0]["link"] in loras[0]["outputs"][0]["links"]

    def test_lora_weights_come_from_the_prompt_tags(self):
        graph = ir.build_template_graph(A1111_META)
        weights = {
            n["widgets_values"][0]: n["widgets_values"][1]
            for n in _nodes_by_type(graph, "LoraLoader")
        }
        assert weights["Detailer.safetensors"] == 0.8
        assert weights["Sunset.safetensors"] == 0.55

    def test_sampler_parameters_are_mapped(self):
        graph = ir.build_template_graph(A1111_META)
        widgets = _nodes_by_type(graph, "KSampler")[0]["widgets_values"]
        seed, _, steps, cfg, sampler, scheduler, denoise = widgets
        assert (seed, steps, cfg, denoise) == (657597278555149, 8, 3.5, 1.0)
        # "DPM++ 2M Karras" splits into a ComfyUI sampler plus a scheduler.
        assert (sampler, scheduler) == ("dpmpp_2m", "karras")

    def test_explicit_scheduler_key_wins(self):
        graph = ir.build_template_graph({"sampler": "Euler a", "scheduler": "sgm uniform"})
        _, _, _, _, sampler, scheduler, _ = _nodes_by_type(graph, "KSampler")[0]["widgets_values"]
        assert (sampler, scheduler) == ("euler_ancestral", "sgm_uniform")

    def test_unknown_sampler_falls_back_to_euler(self):
        graph = ir.build_template_graph({"sampler": "Some Future Sampler"})
        assert _nodes_by_type(graph, "KSampler")[0]["widgets_values"][4] == "euler"

    def test_dimensions_from_width_and_height(self):
        graph = ir.build_template_graph(A1111_META)
        assert _nodes_by_type(graph, "EmptyLatentImage")[0]["widgets_values"] == [832, 1248, 1]

    def test_dimensions_fall_back_to_the_size_string(self):
        graph = ir.build_template_graph({"Size": "768x1024"})
        assert _nodes_by_type(graph, "EmptyLatentImage")[0]["widgets_values"] == [768, 1024, 1]

    def test_dimensions_default_when_absent(self):
        graph = ir.build_template_graph({})
        assert _nodes_by_type(graph, "EmptyLatentImage")[0]["widgets_values"] == [512, 512, 1]

    def test_prompts_land_on_the_encoders(self):
        graph = ir.build_template_graph(A1111_META)
        positive, negative = _nodes_by_type(graph, "CLIPTextEncode")
        assert positive["widgets_values"][0] == A1111_META["prompt"]
        assert negative["widgets_values"][0] == "blurry"

    def test_extension_is_appended_only_when_missing(self):
        graph = ir.build_template_graph({"Model": "epicrealism"})
        assert _nodes_by_type(graph, "CheckpointLoaderSimple")[0]["widgets_values"] == [
            "epicrealism.safetensors"
        ]

    def test_installed_filenames_override_the_guess(self):
        graph = ir.build_template_graph(
            A1111_META, {"krea2_turbo_fp8_scaled.safetensors": "sdxl/real.safetensors"}
        )
        assert _nodes_by_type(graph, "CheckpointLoaderSimple")[0]["widgets_values"] == [
            "sdxl/real.safetensors"
        ]

    def test_empty_meta_still_produces_a_loadable_graph(self):
        graph = ir.build_template_graph(None)
        assert ir.is_comfy_graph(graph)
        assert _nodes_by_type(graph, "LoraLoader") == []


class TestIsComfyGraph:
    @pytest.mark.parametrize("data", [None, {}, {"nodes": "no"}, [], "graph"])
    def test_rejects_non_graphs(self, data):
        assert ir.is_comfy_graph(data) is False

    def test_accepts_a_node_list(self):
        assert ir.is_comfy_graph({"nodes": []}) is True
