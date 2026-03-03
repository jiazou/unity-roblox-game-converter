"""Fine-grained unit tests for modules/material_mapper.py.

Tests internal functions: shader identification, property parsing,
texture operation generation, companion scripts, UNCONVERTED.md
formatting, and edge cases.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modules.material_mapper import (
    MaterialConversionResult,
    MaterialMapResult,
    ParsedMaterial,
    RobloxMaterialDef,
    ShaderInfo,
    TextureOperation,
    UnconvertedFeature,
    _build_guid_map,
    _clean_unity_yaml,
    _color_luminance,
    _color_rgb,
    _color_to_tuple,
    _convert_material,
    _generate_unconverted_md,
    _get_offset,
    _get_tiling,
    _identify_shader,
    _is_black,
    _is_white,
    _parse_colors,
    _parse_floats,
    _parse_material,
    _parse_shader_source,
    _parse_tex_envs,
    _pipeline_label,
    _resolve_texture,
    _safe_filename,
    _process_textures,
    map_materials,
)
from tests.conftest import make_meta


# ── YAML cleaning ─────────────────────────────────────────────────────


class TestCleanUnityYaml:
    def test_strips_yaml_header(self) -> None:
        text = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!21 &2100000\nMaterial:\n  m_Name: Test\n"
        cleaned = _clean_unity_yaml(text)
        assert "%YAML" not in cleaned
        assert "%TAG" not in cleaned
        assert "--- !u!" not in cleaned
        assert "Material:" in cleaned

    def test_preserves_content(self) -> None:
        text = "Material:\n  m_Name: Test\n  value: 42\n"
        assert _clean_unity_yaml(text) == text


# ── Property parsing helpers ──────────────────────────────────────────


class TestParseTexEnvs:
    def test_v3_format(self) -> None:
        raw = [
            {"_MainTex": {"m_Texture": {"fileID": 2800000, "guid": "abc"}, "m_Scale": {"x": 1, "y": 1}}},
        ]
        result = _parse_tex_envs(raw)
        assert "_MainTex" in result
        assert result["_MainTex"]["m_Texture"]["guid"] == "abc"

    def test_v2_format(self) -> None:
        raw = [
            {"first": {"name": "_MainTex"}, "second": {"m_Texture": {"fileID": 2800000, "guid": "def"}}},
        ]
        result = _parse_tex_envs(raw)
        assert "_MainTex" in result
        assert result["_MainTex"]["m_Texture"]["guid"] == "def"

    def test_none_input(self) -> None:
        assert _parse_tex_envs(None) == {}

    def test_non_list_input(self) -> None:
        assert _parse_tex_envs("bad") == {}

    def test_non_dict_entries_skipped(self) -> None:
        raw = [42, "bad", None, {"_MainTex": {"m_Texture": {"fileID": 1}}}]
        result = _parse_tex_envs(raw)
        assert "_MainTex" in result


class TestParseFloats:
    def test_v3_format(self) -> None:
        raw = [{"_Metallic": 0.5}, {"_Glossiness": 0.8}]
        result = _parse_floats(raw)
        assert result["_Metallic"] == 0.5
        assert result["_Glossiness"] == 0.8

    def test_v2_format(self) -> None:
        raw = [{"first": {"name": "_Metallic"}, "second": 0.5}]
        result = _parse_floats(raw)
        assert result["_Metallic"] == 0.5

    def test_none_input(self) -> None:
        assert _parse_floats(None) == {}

    def test_integer_values(self) -> None:
        raw = [{"_Mode": 0}]
        result = _parse_floats(raw)
        assert result["_Mode"] == 0.0


class TestParseColors:
    def test_v3_format(self) -> None:
        raw = [{"_Color": {"r": 1, "g": 0.5, "b": 0, "a": 1}}]
        result = _parse_colors(raw)
        assert "_Color" in result
        assert result["_Color"]["r"] == 1

    def test_v2_format(self) -> None:
        raw = [{"first": {"name": "_Color"}, "second": {"r": 0.8, "g": 0.2, "b": 0.1, "a": 1}}]
        result = _parse_colors(raw)
        assert result["_Color"]["r"] == 0.8

    def test_none_input(self) -> None:
        assert _parse_colors(None) == {}


# ── Texture resolution ────────────────────────────────────────────────


class TestResolveTexture:
    def test_valid_ref(self) -> None:
        entry = {"m_Texture": {"fileID": 2800000, "guid": "abc123", "type": 3}}
        guid_map = {"abc123": Path("/tex/albedo.png")}
        guid, path = _resolve_texture(entry, guid_map)
        assert guid == "abc123"
        assert path == Path("/tex/albedo.png")

    def test_zero_file_id(self) -> None:
        entry = {"m_Texture": {"fileID": 0, "guid": "", "type": 0}}
        guid, path = _resolve_texture(entry, {})
        assert guid is None
        assert path is None

    def test_unresolvable_guid(self) -> None:
        entry = {"m_Texture": {"fileID": 1, "guid": "missing", "type": 3}}
        guid, path = _resolve_texture(entry, {})
        assert guid == "missing"
        assert path is None

    def test_missing_m_texture(self) -> None:
        entry = {"m_Scale": {"x": 1, "y": 1}}
        guid, path = _resolve_texture(entry, {})
        assert guid is None
        assert path is None


class TestGetTilingAndOffset:
    def test_tiling_default(self) -> None:
        assert _get_tiling({}) == (1.0, 1.0)

    def test_tiling_custom(self) -> None:
        entry = {"m_Scale": {"x": 2, "y": 3}}
        assert _get_tiling(entry) == (2.0, 3.0)

    def test_offset_default(self) -> None:
        assert _get_offset({}) == (0.0, 0.0)

    def test_offset_custom(self) -> None:
        entry = {"m_Offset": {"x": 0.5, "y": -0.25}}
        assert _get_offset(entry) == (0.5, -0.25)


# ── Color helpers ─────────────────────────────────────────────────────


class TestColorHelpers:
    def test_is_white_true(self) -> None:
        assert _is_white((1.0, 1.0, 1.0)) is True
        assert _is_white((0.999, 0.999, 0.999)) is True

    def test_is_white_false(self) -> None:
        assert _is_white((0.5, 1.0, 1.0)) is False

    def test_is_black_true(self) -> None:
        assert _is_black((0.0, 0.0, 0.0)) is True
        assert _is_black((0.005, 0.005, 0.005)) is True

    def test_is_black_false(self) -> None:
        assert _is_black((0.5, 0.0, 0.0)) is False

    def test_color_luminance(self) -> None:
        # Pure white
        assert abs(_color_luminance(1.0, 1.0, 1.0) - 1.0) < 0.001
        # Pure black
        assert _color_luminance(0.0, 0.0, 0.0) == 0.0
        # Green is dominant
        green_lum = _color_luminance(0.0, 1.0, 0.0)
        red_lum = _color_luminance(1.0, 0.0, 0.0)
        assert green_lum > red_lum

    def test_color_to_tuple(self) -> None:
        c = {"r": 0.8, "g": 0.6, "b": 0.4, "a": 0.9}
        assert _color_to_tuple(c) == (0.8, 0.6, 0.4, 0.9)

    def test_color_to_tuple_defaults(self) -> None:
        c = {}
        # Defaults: r=1, g=1, b=1, a=1
        assert _color_to_tuple(c) == (1.0, 1.0, 1.0, 1.0)

    def test_color_rgb(self) -> None:
        c = {"r": 0.5, "g": 0.3, "b": 0.1}
        assert _color_rgb(c) == (0.5, 0.3, 0.1)

    def test_color_rgb_defaults(self) -> None:
        c = {}
        assert _color_rgb(c) == (0.0, 0.0, 0.0)


# ── Filename sanitization ────────────────────────────────────────────


class TestSafeFilename:
    def test_simple_name(self) -> None:
        assert _safe_filename("TestMat", "_color.png") == "TestMat_color.png"

    def test_spaces_replaced(self) -> None:
        result = _safe_filename("My Material", "_color.png")
        assert " " not in result
        assert result.endswith("_color.png")

    def test_special_chars_replaced(self) -> None:
        result = _safe_filename("Mat (1)/Copy", "_normal.png")
        assert "(" not in result
        assert "/" not in result


# ── Pipeline label ────────────────────────────────────────────────────


class TestPipelineLabel:
    @pytest.mark.parametrize("category,expected", [
        ("standard", "BUILTIN"),
        ("standard_specular", "BUILTIN"),
        ("urp_lit", "URP"),
        ("urp_unlit", "URP"),
        ("hdrp_lit", "HDRP"),
        ("legacy_diffuse", "LEGACY"),
        ("legacy_bumped", "LEGACY"),
        ("particle_alpha", "PARTICLE"),
        ("particle_additive", "PARTICLE"),
        ("sprite", "PARTICLE"),
        ("custom", "CUSTOM"),
        ("custom_unlit", "CUSTOM"),
        ("custom_blinking", "CUSTOM"),
        ("vertex_color", "CUSTOM"),
        ("unknown", "UNKNOWN"),
    ])
    def test_pipeline_labels(self, category: str, expected: str) -> None:
        assert _pipeline_label(category) == expected


# ── Shader identification ─────────────────────────────────────────────


class TestIdentifyShader:
    def test_builtin_standard(self) -> None:
        shader = _identify_shader({"fileID": 46}, {}, set())
        assert shader.name == "Standard"
        assert shader.category == "standard"

    def test_builtin_specular(self) -> None:
        shader = _identify_shader({"fileID": 45}, {}, set())
        assert shader.name == "Standard (Specular setup)"

    def test_builtin_legacy_diffuse(self) -> None:
        shader = _identify_shader({"fileID": 10720}, {}, set())
        assert shader.category == "legacy_diffuse"

    def test_builtin_particle_alpha(self) -> None:
        shader = _identify_shader({"fileID": 10751}, {}, set())
        assert shader.category == "particle_alpha"
        assert shader.is_transparent is True

    def test_builtin_sprite(self) -> None:
        shader = _identify_shader({"fileID": 200}, {}, set())
        assert shader.category == "sprite"

    def test_urp_lit_detected_by_properties(self) -> None:
        props = {"_BaseMap", "_BaseColor", "_BumpMap", "_Metallic"}
        shader = _identify_shader({"fileID": 0}, {}, props)
        assert shader.category == "urp_lit"

    def test_urp_unlit_detected_by_properties(self) -> None:
        props = {"_BaseMap", "_BaseColor"}
        shader = _identify_shader({"fileID": 0}, {}, props)
        assert shader.category == "urp_unlit"

    def test_unknown_shader(self) -> None:
        shader = _identify_shader({"fileID": 0}, {}, set())
        assert shader.category == "unknown"


class TestParseShaderSource:
    def test_simple_shader(self, tmp_path: Path) -> None:
        shader_code = textwrap.dedent("""\
            Shader "Custom/MyShader" {
                Properties {
                    _MainTex ("Texture", 2D) = "white" {}
                    _Color ("Color", Color) = (1,1,1,1)
                }
                SubShader {
                    Pass {
                        CGPROGRAM
                        sampler2D _MainTex;
                        fixed4 _Color;
                        ENDCG
                    }
                }
            }
        """)
        shader_path = tmp_path / "Custom.shader"
        shader_path.write_text(shader_code, encoding="utf-8")
        info = _parse_shader_source(shader_path)

        assert info.name == "Custom/MyShader"
        assert info.reads_maintex is True
        assert info.reads_color is True
        assert info.is_transparent is False

    def test_transparent_shader(self, tmp_path: Path) -> None:
        shader_code = textwrap.dedent("""\
            Shader "Custom/Alpha" {
                Properties {
                    _MainTex ("Texture", 2D) = "white" {}
                }
                SubShader {
                    Tags { "RenderType" = "Transparent" }
                    Blend SrcAlpha OneMinusSrcAlpha
                    ZWrite Off
                    Pass {
                        CGPROGRAM
                        sampler2D _MainTex;
                        ENDCG
                    }
                }
            }
        """)
        shader_path = tmp_path / "Alpha.shader"
        shader_path.write_text(shader_code, encoding="utf-8")
        info = _parse_shader_source(shader_path)

        assert info.is_transparent is True

    def test_vertex_color_shader(self, tmp_path: Path) -> None:
        shader_code = textwrap.dedent("""\
            Shader "Custom/VertexColor" {
                SubShader {
                    Pass {
                        CGPROGRAM
                        float4 frag(v2f i) : SV_Target {
                            return i.color;
                        }
                        ENDCG
                    }
                }
            }
        """)
        shader_path = tmp_path / "VC.shader"
        shader_path.write_text(shader_code, encoding="utf-8")
        info = _parse_shader_source(shader_path)

        assert info.uses_vertex_colors is True

    def test_short_shader_conservative_defaults(self, tmp_path: Path) -> None:
        """Very short shader source → conservative: reads everything."""
        shader_path = tmp_path / "Short.shader"
        shader_path.write_text('Shader "S" { Fallback "Diffuse" }', encoding="utf-8")
        info = _parse_shader_source(shader_path)
        assert info.reads_color is True
        assert info.reads_maintex is True

    def test_unreadable_shader_conservative(self, tmp_path: Path) -> None:
        """Non-existent shader → conservative defaults."""
        info = _parse_shader_source(tmp_path / "missing.shader")
        assert info.reads_color is True
        assert info.reads_maintex is True

    def test_include_resolution(self, tmp_path: Path) -> None:
        """Shader with #include should resolve included file."""
        inc_code = "sampler2D _MainTex;\nfixed4 _Color;\n"
        (tmp_path / "Common.cginc").write_text(inc_code, encoding="utf-8")

        shader_code = textwrap.dedent("""\
            Shader "Custom/WithInclude" {
                SubShader {
                    Pass {
                        CGPROGRAM
                        #include "Common.cginc"
                        float4 frag() : SV_Target { return tex2D(_MainTex, uv) * _Color; }
                        ENDCG
                    }
                }
            }
        """)
        shader_path = tmp_path / "WithInclude.shader"
        shader_path.write_text(shader_code, encoding="utf-8")
        info = _parse_shader_source(shader_path)
        assert info.reads_maintex is True
        assert info.reads_color is True


# ── Material conversion core ──────────────────────────────────────────


class TestConvertMaterial:
    def _make_parsed(self, **kwargs) -> ParsedMaterial:
        defaults = dict(
            name="Test",
            path=Path("/test/Test.mat"),
            shader=ShaderInfo("Standard", "standard", False, False, True, True),
        )
        defaults.update(kwargs)
        return ParsedMaterial(**defaults)

    def test_opaque_standard_no_textures(self) -> None:
        parsed = self._make_parsed(
            albedo_color=(0.5, 0.3, 0.1, 1.0),
        )
        result = _convert_material(parsed)
        assert result.roblox_def is not None
        assert result.roblox_def.base_part_color == (0.5, 0.3, 0.1)
        assert result.roblox_def.color_map is None
        assert result.roblox_def.alpha_mode == "Opaque"

    def test_standard_with_texture(self, tmp_path: Path) -> None:
        tex = tmp_path / "albedo.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=tex,
            albedo_tex_guid="abc",
            albedo_color=(1.0, 1.0, 1.0, 1.0),
        )
        result = _convert_material(parsed)
        assert result.roblox_def.color_map is not None
        assert len(result.texture_ops) >= 1

    def test_standard_color_tint(self, tmp_path: Path) -> None:
        tex = tmp_path / "albedo.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=tex,
            albedo_tex_guid="abc",
            albedo_color=(0.8, 0.2, 0.1, 1.0),
        )
        result = _convert_material(parsed)
        assert result.roblox_def.color_tint != (1.0, 1.0, 1.0)

    def test_transparency_from_alpha(self) -> None:
        parsed = self._make_parsed(
            albedo_color=(1.0, 1.0, 1.0, 0.5),
        )
        result = _convert_material(parsed)
        assert result.roblox_def.base_part_transparency == pytest.approx(0.5)

    def test_metallic_scalar(self) -> None:
        parsed = self._make_parsed(metallic_value=0.8)
        result = _convert_material(parsed)
        assert result.roblox_def.metalness_map is not None

    def test_roughness_from_smoothness(self) -> None:
        parsed = self._make_parsed(smoothness_value=0.7)
        result = _convert_material(parsed)
        assert result.roblox_def.roughness_map is not None

    def test_metallic_texture(self, tmp_path: Path) -> None:
        tex = tmp_path / "metallic.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(metallic_tex_path=tex)
        result = _convert_material(parsed)
        assert result.roblox_def.metalness_map is not None
        assert result.roblox_def.roughness_map is not None
        # Should have extract_channel operations
        channel_ops = [op for op in result.texture_ops if op.operation == "extract_channel"]
        assert len(channel_ops) == 2

    def test_normal_map(self, tmp_path: Path) -> None:
        tex = tmp_path / "normal.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(normal_tex_path=tex, normal_scale=1.0)
        result = _convert_material(parsed)
        assert result.roblox_def.normal_map is not None

    def test_normal_scale_baked(self, tmp_path: Path) -> None:
        tex = tmp_path / "normal.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(normal_tex_path=tex, normal_scale=0.5)
        result = _convert_material(parsed)
        assert result.roblox_def.normal_map is not None
        bake_warning = [w for w in result.warnings if "Normal scale" in w]
        assert len(bake_warning) > 0

    def test_emission_with_texture(self, tmp_path: Path) -> None:
        tex = tmp_path / "emission.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(
            emission_tex_path=tex,
            emission_color=(1.0, 0.5, 0.0),
        )
        result = _convert_material(parsed)
        assert result.roblox_def.emissive_mask is not None
        assert result.roblox_def.emissive_strength > 0

    def test_emission_color_only(self) -> None:
        parsed = self._make_parsed(emission_color=(0.5, 0.5, 0.0))
        result = _convert_material(parsed)
        assert result.roblox_def.emissive_mask is not None

    def test_render_mode_cutout(self, tmp_path: Path) -> None:
        tex = tmp_path / "albedo.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(
            render_mode=1,
            albedo_tex_path=tex,
            albedo_tex_guid="abc",
            alpha_cutoff=0.3,
        )
        result = _convert_material(parsed)
        assert result.roblox_def.alpha_mode == "Transparency"

    def test_render_mode_transparent(self) -> None:
        parsed = self._make_parsed(render_mode=3)
        result = _convert_material(parsed)
        assert result.roblox_def.alpha_mode == "Transparency"

    def test_vertex_color_shader_unconverted(self) -> None:
        parsed = self._make_parsed(
            shader=ShaderInfo("VC", "vertex_color", False, True, False, False),
        )
        result = _convert_material(parsed)
        assert result.roblox_def is None
        assert len(result.unconverted) > 0

    def test_unknown_shader_unconverted(self) -> None:
        parsed = self._make_parsed(
            shader=ShaderInfo("???", "unknown", False, False, True, True),
        )
        result = _convert_material(parsed)
        assert result.roblox_def is None

    def test_fully_converted_flag(self) -> None:
        parsed = self._make_parsed(
            albedo_color=(0.5, 0.5, 0.5, 1.0),
        )
        result = _convert_material(parsed)
        assert result.fully_converted is True

    def test_partially_converted_has_unconverted(self) -> None:
        parsed = self._make_parsed(
            shader=ShaderInfo("Custom", "custom", True, True, True, True),
            albedo_color=(1.0, 1.0, 1.0, 1.0),
        )
        result = _convert_material(parsed)
        # Transparent + vertex colors → unconverted entries
        assert result.roblox_def is not None
        assert len(result.unconverted) > 0
        assert result.fully_converted is False

    def test_particle_shader(self) -> None:
        parsed = self._make_parsed(
            shader=ShaderInfo("Particles/Alpha Blended", "particle_alpha", True, False, False, True),
            tint_color=(1.0, 0.5, 0.0, 1.0),
        )
        result = _convert_material(parsed)
        assert result.pipeline == "PARTICLE"
        assert result.roblox_def.alpha_mode == "Transparency"

    def test_particle_additive_unconverted(self) -> None:
        parsed = self._make_parsed(
            shader=ShaderInfo("Particles/Additive", "particle_additive", True, False, False, True),
        )
        result = _convert_material(parsed)
        additive_entries = [u for u in result.unconverted if "Additive" in u.feature_name]
        assert len(additive_entries) > 0

    def test_detail_map_unconverted(self) -> None:
        parsed = self._make_parsed(
            active_tex_names={"_DetailAlbedoMap"},
        )
        result = _convert_material(parsed)
        detail_entries = [u for u in result.unconverted if "Detail" in u.feature_name]
        assert len(detail_entries) > 0

    def test_parallax_map_unconverted(self) -> None:
        parsed = self._make_parsed(
            active_tex_names={"_ParallaxMap"},
        )
        result = _convert_material(parsed)
        height_entries = [u for u in result.unconverted if "Height" in u.feature_name or "parallax" in u.feature_name.lower()]
        assert len(height_entries) > 0

    def test_detail_albedo_composite_op(self, tmp_path: Path) -> None:
        """Detail albedo map with resolved texture should produce composite_detail op."""
        albedo = tmp_path / "albedo.png"
        albedo.write_bytes(b"PNG")
        detail = tmp_path / "detail.png"
        detail.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=albedo,
            albedo_tex_guid="abc",
            detail_albedo_tex_path=detail,
            detail_tiling=(2.0, 2.0),
            active_tex_names={"_DetailAlbedoMap"},
        )
        result = _convert_material(parsed)
        composite_ops = [op for op in result.texture_ops if op.operation == "composite_detail"]
        assert len(composite_ops) == 1
        assert composite_ops[0].params["detail_tiling_x"] == 2.0

    def test_detail_normal_blend_op(self, tmp_path: Path) -> None:
        """Detail normal map with resolved texture should produce blend_normal_detail op."""
        albedo = tmp_path / "albedo.png"
        albedo.write_bytes(b"PNG")
        normal = tmp_path / "normal.png"
        normal.write_bytes(b"PNG")
        detail_normal = tmp_path / "detail_normal.png"
        detail_normal.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=albedo,
            albedo_tex_guid="abc",
            normal_tex_path=normal,
            detail_normal_tex_path=detail_normal,
            detail_normal_scale=0.5,
            active_tex_names={"_DetailNormalMap"},
        )
        result = _convert_material(parsed)
        blend_ops = [op for op in result.texture_ops if op.operation == "blend_normal_detail"]
        assert len(blend_ops) == 1
        assert blend_ops[0].params["detail_normal_scale"] == 0.5

    def test_heightmap_to_normal_with_existing_normal(self, tmp_path: Path) -> None:
        """Height map with existing normal should produce heightmap_to_normal op with blend."""
        albedo = tmp_path / "albedo.png"
        albedo.write_bytes(b"PNG")
        normal = tmp_path / "normal.png"
        normal.write_bytes(b"PNG")
        height = tmp_path / "height.png"
        height.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=albedo,
            albedo_tex_guid="abc",
            normal_tex_path=normal,
            height_tex_path=height,
            height_strength=0.05,
        )
        result = _convert_material(parsed)
        h2n_ops = [op for op in result.texture_ops if op.operation == "heightmap_to_normal"]
        assert len(h2n_ops) == 1
        assert h2n_ops[0].params["strength"] == 0.05
        assert h2n_ops[0].params["base_normal_path"] == str(normal)

    def test_heightmap_to_normal_generates_normal(self, tmp_path: Path) -> None:
        """Height map without existing normal should generate a new normal map."""
        albedo = tmp_path / "albedo.png"
        albedo.write_bytes(b"PNG")
        height = tmp_path / "height.png"
        height.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=albedo,
            albedo_tex_guid="abc",
            height_tex_path=height,
            height_strength=0.03,
        )
        result = _convert_material(parsed)
        h2n_ops = [op for op in result.texture_ops if op.operation == "heightmap_to_normal"]
        assert len(h2n_ops) == 1
        assert result.roblox_def.normal_map is not None
        assert "normal" in result.roblox_def.normal_map.lower()

    def test_tiling_pre_tile(self, tmp_path: Path) -> None:
        """Tiling within PRE_TILE_MAX_FACTOR should produce a pre_tile op."""
        tex = tmp_path / "albedo.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=tex,
            albedo_tex_guid="abc",
            albedo_tex_tiling=(2.0, 2.0),
        )
        result = _convert_material(parsed)
        tile_ops = [op for op in result.texture_ops if op.operation == "pre_tile"]
        assert len(tile_ops) == 1

    def test_tiling_too_large_unconverted(self, tmp_path: Path) -> None:
        """Tiling beyond PRE_TILE_MAX_FACTOR should log unconverted."""
        tex = tmp_path / "albedo.png"
        tex.write_bytes(b"PNG")
        parsed = self._make_parsed(
            albedo_tex_path=tex,
            albedo_tex_guid="abc",
            albedo_tex_tiling=(10.0, 10.0),
        )
        result = _convert_material(parsed)
        tiling_entries = [u for u in result.unconverted if "tiling" in u.feature_name.lower()]
        assert len(tiling_entries) > 0

    def test_blinking_companion_script(self) -> None:
        parsed = self._make_parsed(
            shader=ShaderInfo("Custom/UnlitBlinking", "custom_blinking", False, False, True, True),
        )
        result = _convert_material(parsed)
        assert len(result.companion_scripts) > 0
        assert "TweenService" in result.companion_scripts[0]

    def test_rotation_companion_script(self) -> None:
        parsed = self._make_parsed(
            shader=ShaderInfo("Custom/CurvedRotation", "custom_rotation", False, False, True, True),
        )
        result = _convert_material(parsed)
        assert len(result.companion_scripts) > 0
        assert "CFrame.Angles" in result.companion_scripts[0]


# ── GUID map building ─────────────────────────────────────────────────


class TestBuildGuidMap:
    def test_returns_dict(self, unity_project: Path) -> None:
        guid_map = _build_guid_map(unity_project)
        assert isinstance(guid_map, dict)
        assert len(guid_map) > 0

    def test_texture_guid_resolved(self, unity_project: Path) -> None:
        guid_map = _build_guid_map(unity_project)
        assert "aaaa0000aaaa0000aaaa0000aaaa0001" in guid_map

    def test_missing_assets_returns_empty(self, tmp_path: Path) -> None:
        guid_map = _build_guid_map(tmp_path / "nonexistent")
        assert guid_map == {}


# ── UNCONVERTED.md generation ─────────────────────────────────────────


class TestGenerateUnconvertedMd:
    def test_creates_file(self, tmp_path: Path) -> None:
        results = []
        path = _generate_unconverted_md(results, "TestProject", tmp_path / "UNCONVERTED.md")
        assert path.exists()
        content = path.read_text()
        assert "Conversion Statistics" in content

    def test_contains_project_name(self, tmp_path: Path) -> None:
        path = _generate_unconverted_md([], "MyGame", tmp_path / "UNCONVERTED.md")
        content = path.read_text()
        assert "MyGame" in content

    def test_statistics_table(self, tmp_path: Path) -> None:
        r1 = MaterialConversionResult(
            material_name="M1", material_path=Path("/m1.mat"),
            shader_name="Standard", pipeline="BUILTIN",
            roblox_def=RobloxMaterialDef(), fully_converted=True,
        )
        r2 = MaterialConversionResult(
            material_name="M2", material_path=Path("/m2.mat"),
            shader_name="Unknown", pipeline="UNKNOWN",
            roblox_def=None,
        )
        path = _generate_unconverted_md([r1, r2], "Proj", tmp_path / "UNCONVERTED.md")
        content = path.read_text()
        assert "Fully converted" in content
        assert "Skipped" in content

    def test_unconverted_feature_listed(self, tmp_path: Path) -> None:
        r = MaterialConversionResult(
            material_name="M1", material_path=Path("/m1.mat"),
            shader_name="Standard", pipeline="BUILTIN",
            roblox_def=RobloxMaterialDef(),
            unconverted=[UnconvertedFeature(
                "Detail map", "_DetailAlbedoMap", "MEDIUM",
                "Bake detail into base texture", True,
            )],
        )
        path = _generate_unconverted_md([r], "Proj", tmp_path / "UNCONVERTED.md")
        content = path.read_text()
        assert "Detail map" in content
        assert "MEDIUM" in content


# ── Parse material from YAML ──────────────────────────────────────────


class TestParseMaterial:
    def test_standard_material(self, tmp_path: Path) -> None:
        from tests.conftest import STANDARD_MAT_YAML
        mat = tmp_path / "Std.mat"
        mat.write_text(STANDARD_MAT_YAML, encoding="utf-8")
        make_meta(mat.with_suffix(".mat.meta"), "eeee0000eeee0000eeee0000eeee0001")

        guid_map = _build_guid_map(tmp_path)
        parsed = _parse_material(mat, guid_map)
        assert parsed is not None
        assert parsed.shader.category == "standard"
        assert parsed.name == "TestStandard"

    def test_invalid_yaml_returns_none(self, tmp_path: Path) -> None:
        mat = tmp_path / "Bad.mat"
        mat.write_text("::: invalid yaml [[[", encoding="utf-8")
        assert _parse_material(mat, {}) is None

    def test_non_material_yaml_returns_none(self, tmp_path: Path) -> None:
        mat = tmp_path / "NotMat.mat"
        mat.write_text("SomeOtherType:\n  key: value\n", encoding="utf-8")
        assert _parse_material(mat, {}) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert _parse_material(tmp_path / "ghost.mat", {}) is None


# ── HDRP shader detection ────────────────────────────────────────────


class TestHDRPDetection:
    def test_hdrp_detected_by_mask_map(self) -> None:
        props = {"_BaseColorMap", "_MaskMap", "_NormalMap", "_NormalScale"}
        info = _identify_shader({"fileID": 0, "guid": "unknown"}, {}, props)
        assert info.category == "hdrp_lit"

    def test_hdrp_not_confused_with_urp(self) -> None:
        # URP uses _BaseMap, not _BaseColorMap
        props = {"_BaseMap", "_Smoothness"}
        info = _identify_shader({"fileID": 0, "guid": "unknown"}, {}, props)
        assert info.category != "hdrp_lit"


# ── Standard Specular → Metallic conversion ──────────────────────────


class TestSpecularToMetallic:
    def test_high_spec_luminance_gives_metallic_one(self) -> None:
        parsed = ParsedMaterial(
            name="HighSpec",
            path=Path("/fake/HighSpec.mat"),
            shader=ShaderInfo("Standard (Specular setup)", "standard_specular",
                              False, False, True, True),
            specular_color=(0.9, 0.9, 0.9),
        )
        result = _convert_material(parsed)
        assert result.roblox_def is not None
        # Should generate a uniform metalness texture at 255
        met_ops = [op for op in result.texture_ops if "metalness" in op.output_filename]
        assert len(met_ops) == 1
        assert met_ops[0].params.get("uniform_value") == 255

    def test_low_spec_luminance_gives_metallic_zero(self) -> None:
        parsed = ParsedMaterial(
            name="LowSpec",
            path=Path("/fake/LowSpec.mat"),
            shader=ShaderInfo("Standard (Specular setup)", "standard_specular",
                              False, False, True, True),
            specular_color=(0.1, 0.1, 0.1),
        )
        result = _convert_material(parsed)
        assert result.roblox_def is not None
        met_ops = [op for op in result.texture_ops if "metalness" in op.output_filename]
        assert len(met_ops) == 1
        assert met_ops[0].params.get("uniform_value") == 0


# ── URP alpha handling ───────────────────────────────────────────────


class TestURPAlpha:
    def test_urp_surface_opaque(self, tmp_path: Path) -> None:
        mat = tmp_path / "URP.mat"
        mat.write_text(textwrap.dedent("""\
            Material:
              m_Name: URPOpaque
              m_Shader: {fileID: 0, guid: urp_lit_guid, type: 0}
              m_SavedProperties:
                serializedVersion: 3
                m_TexEnvs:
                - _BaseMap:
                    m_Texture: {fileID: 0}
                    m_Scale: {x: 1, y: 1}
                    m_Offset: {x: 0, y: 0}
                m_Floats:
                - _Surface: 0
                - _Metallic: 0
                - _Smoothness: 0.5
                m_Colors:
                - _BaseColor: {r: 1, g: 1, b: 1, a: 1}
        """), encoding="utf-8")
        parsed = _parse_material(mat, {})
        assert parsed is not None
        assert parsed.render_mode == 0  # Opaque

    def test_urp_surface_cutout(self, tmp_path: Path) -> None:
        mat = tmp_path / "URPCut.mat"
        mat.write_text(textwrap.dedent("""\
            Material:
              m_Name: URPCutout
              m_Shader: {fileID: 0, guid: urp_lit_guid, type: 0}
              m_SavedProperties:
                serializedVersion: 3
                m_TexEnvs:
                - _BaseMap:
                    m_Texture: {fileID: 0}
                    m_Scale: {x: 1, y: 1}
                    m_Offset: {x: 0, y: 0}
                m_Floats:
                - _Surface: 1
                - _AlphaClip: 1
                - _Metallic: 0
                - _Smoothness: 0.5
                m_Colors:
                - _BaseColor: {r: 1, g: 1, b: 1, a: 1}
        """), encoding="utf-8")
        parsed = _parse_material(mat, {})
        assert parsed is not None
        assert parsed.render_mode == 1  # Cutout

    def test_urp_surface_transparent(self, tmp_path: Path) -> None:
        mat = tmp_path / "URPTrans.mat"
        mat.write_text(textwrap.dedent("""\
            Material:
              m_Name: URPTransparent
              m_Shader: {fileID: 0, guid: urp_lit_guid, type: 0}
              m_SavedProperties:
                serializedVersion: 3
                m_TexEnvs:
                - _BaseMap:
                    m_Texture: {fileID: 0}
                    m_Scale: {x: 1, y: 1}
                    m_Offset: {x: 0, y: 0}
                m_Floats:
                - _Surface: 1
                - _AlphaClip: 0
                - _Metallic: 0
                - _Smoothness: 0.5
                m_Colors:
                - _BaseColor: {r: 1, g: 1, b: 1, a: 1}
        """), encoding="utf-8")
        parsed = _parse_material(mat, {})
        assert parsed is not None
        assert parsed.render_mode == 2  # Fade/Transparent


# ── Smoothness from albedo alpha ─────────────────────────────────────


class TestSmoothnessSource:
    def test_smoothness_from_metallic_alpha_default(self, tmp_path: Path) -> None:
        met_tex = tmp_path / "met.png"
        met_tex.write_bytes(b"\x89PNG")  # minimal file to pass exists()
        parsed = ParsedMaterial(
            name="DefaultSmooth",
            path=Path("/fake/DefaultSmooth.mat"),
            shader=ShaderInfo("Standard", "standard", False, False, True, True),
            metallic_tex_path=met_tex,
            smoothness_source=0,
            smoothness_scale=1.0,
        )
        result = _convert_material(parsed)
        # Roughness extracted from metallic texture A channel (default)
        rough_ops = [op for op in result.texture_ops
                     if "roughness" in op.output_filename and op.operation == "extract_channel"]
        assert len(rough_ops) == 1
        assert rough_ops[0].source_path == met_tex
        assert rough_ops[0].channel == "A"

    def test_smoothness_from_albedo_alpha(self, tmp_path: Path) -> None:
        met_tex = tmp_path / "met.png"
        met_tex.write_bytes(b"\x89PNG")
        albedo_tex = tmp_path / "albedo.png"
        albedo_tex.write_bytes(b"\x89PNG")
        parsed = ParsedMaterial(
            name="AlbedoSmooth",
            path=Path("/fake/AlbedoSmooth.mat"),
            shader=ShaderInfo("Standard", "standard", False, False, True, True),
            metallic_tex_path=met_tex,
            albedo_tex_path=albedo_tex,
            smoothness_source=1,
            smoothness_scale=1.0,
        )
        result = _convert_material(parsed)
        rough_ops = [op for op in result.texture_ops
                     if "roughness" in op.output_filename and op.operation == "extract_channel"]
        assert len(rough_ops) == 1
        assert rough_ops[0].source_path == albedo_tex
        assert rough_ops[0].channel == "A"


# ── Legacy shader PBR handling ───────────────────────────────────────


class TestLegacyShaderPBR:
    def test_legacy_bumped_has_normal_map(self, tmp_path: Path) -> None:
        bump_tex = tmp_path / "bump.png"
        bump_tex.write_bytes(b"\x89PNG")
        parsed = ParsedMaterial(
            name="LegacyBumped",
            path=Path("/fake/LegacyBumped.mat"),
            shader=ShaderInfo("Legacy Shaders/Bumped Diffuse", "legacy_bumped",
                              False, False, True, True),
            normal_tex_path=bump_tex,
        )
        result = _convert_material(parsed)
        assert result.roblox_def is not None
        assert result.roblox_def.normal_map is not None
        assert "normal" in result.roblox_def.normal_map

    def test_legacy_specular_converts_to_metallic(self) -> None:
        parsed = ParsedMaterial(
            name="LegacySpec",
            path=Path("/fake/LegacySpec.mat"),
            shader=ShaderInfo("Legacy Shaders/Specular", "legacy_specular",
                              False, False, True, True),
            specular_color=(0.8, 0.8, 0.8),
            smoothness_value=0.5,
        )
        result = _convert_material(parsed)
        assert result.roblox_def is not None
        # High specular → metallic=1
        met_ops = [op for op in result.texture_ops if "metalness" in op.output_filename]
        assert len(met_ops) == 1
        assert met_ops[0].params.get("uniform_value") == 255


# ── Directional Light → Lighting ─────────────────────────────────────


class TestDirectionalLight:
    def test_directional_light_collected(self) -> None:
        from modules.conversion_helpers import (
            convert_light_components,
            directional_lights_to_lighting,
        )
        from modules.scene_parser import ComponentData

        part = __import__("modules.rbxl_writer", fromlist=["RbxPartEntry"]).RbxPartEntry(name="DirLight")
        comp = ComponentData(
            component_type="Light",
            file_id="10",
            properties={
                "m_Type": 1,
                "m_Color": {"r": 1.0, "g": 0.9, "b": 0.8},
                "m_Intensity": 1.5,
                "m_Shadows": 0,
            },
        )
        dir_lights: list[dict] = []
        convert_light_components(part, [comp], dir_lights)
        assert len(dir_lights) == 1
        assert dir_lights[0]["intensity"] == 1.5

        lighting = directional_lights_to_lighting(dir_lights)
        assert lighting is not None
        assert lighting.brightness == 3.0
        assert lighting.color_shift_top == (1.0, 0.9, 0.8)


# ── Primitive shape detection ────────────────────────────────────────


class TestPrimitiveShapeDetection:
    def test_cube_detected_as_block(self) -> None:
        from modules.conversion_helpers import _detect_primitive_shape
        from modules.scene_parser import SceneNode, ComponentData

        node = SceneNode(name="Cube", file_id="1", active=True, layer=0, tag="Untagged")
        node.components.append(ComponentData(
            component_type="MeshFilter",
            file_id="2",
            properties={
                "m_Mesh": {
                    "fileID": 10202,
                    "guid": "0000000000000000e000000000000000",
                    "type": 0,
                }
            },
        ))
        assert _detect_primitive_shape(node) == "Block"

    def test_sphere_detected_as_ball(self) -> None:
        from modules.conversion_helpers import _detect_primitive_shape
        from modules.scene_parser import SceneNode, ComponentData

        node = SceneNode(name="Sphere", file_id="1", active=True, layer=0, tag="Untagged")
        node.components.append(ComponentData(
            component_type="MeshFilter",
            file_id="2",
            properties={
                "m_Mesh": {
                    "fileID": 10207,
                    "guid": "0000000000000000e000000000000000",
                    "type": 0,
                }
            },
        ))
        assert _detect_primitive_shape(node) == "Ball"

    def test_no_mesh_filter_returns_none(self) -> None:
        from modules.conversion_helpers import _detect_primitive_shape
        from modules.scene_parser import SceneNode

        node = SceneNode(name="Empty", file_id="1", active=True, layer=0, tag="Untagged")
        result = _detect_primitive_shape(node)
        # Falls back to name-based detection, "Empty" doesn't match
        assert result is None


# ── parts_written counting ───────────────────────────────────────────


class TestPartsWrittenCounting:
    def test_count_includes_children(self, tmp_path: Path) -> None:
        from modules.rbxl_writer import RbxPartEntry, write_rbxl

        child1 = RbxPartEntry(name="C1")
        child2 = RbxPartEntry(name="C2")
        parent = RbxPartEntry(name="P", children=[child1, child2])
        rbxl = tmp_path / "test.rbxl"
        result = write_rbxl([parent], [], rbxl)
        assert result.parts_written == 3  # 1 parent + 2 children

    def test_deeply_nested_counting(self, tmp_path: Path) -> None:
        from modules.rbxl_writer import RbxPartEntry, write_rbxl

        leaf = RbxPartEntry(name="Leaf")
        mid = RbxPartEntry(name="Mid", children=[leaf])
        root = RbxPartEntry(name="Root", children=[mid])
        rbxl = tmp_path / "test.rbxl"
        result = write_rbxl([root], [], rbxl)
        assert result.parts_written == 3  # root + mid + leaf


# ── Camera extraction ────────────────────────────────────────────────


class TestCameraExtraction:
    def test_camera_from_main_camera_node(self) -> None:
        from modules.conversion_helpers import _extract_camera_from_scenes
        from modules.scene_parser import ParsedScene, SceneNode, ComponentData

        cam_node = SceneNode(
            name="Main Camera", file_id="1",
            active=True, layer=0, tag="MainCamera",
            position=(0.0, 10.0, -20.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
        )
        cam_node.components.append(ComponentData(
            component_type="Camera",
            file_id="2",
            properties={"field of view": 75.0, "near clip plane": 0.5, "far clip plane": 500.0},
        ))
        scene = ParsedScene(
            scene_path=Path("/s.unity"),
            roots=[cam_node],
            all_nodes={"1": cam_node},
        )
        config = _extract_camera_from_scenes([scene], {"1": cam_node})
        assert config is not None
        assert config.field_of_view == 75.0
        assert config.near_clip == 0.5
        assert config.far_clip == 500.0

    def test_no_camera_returns_none(self) -> None:
        from modules.conversion_helpers import _extract_camera_from_scenes
        from modules.scene_parser import ParsedScene, SceneNode

        node = SceneNode(name="Empty", file_id="1", active=True, layer=0, tag="Untagged")
        scene = ParsedScene(
            scene_path=Path("/s.unity"),
            roots=[node],
            all_nodes={"1": node},
        )
        assert _extract_camera_from_scenes([scene], {"1": node}) is None


# ── Unlit game detection ─────────────────────────────────────────────


class TestUnlitDetection:
    def test_mostly_unlit_detected(self) -> None:
        from modules.conversion_helpers import _detect_unlit_game
        from types import SimpleNamespace

        results = [
            SimpleNamespace(pipeline="CUSTOM", shader_name="Unlit/Texture"),
            SimpleNamespace(pipeline="CUSTOM", shader_name="Unlit/Color"),
            SimpleNamespace(pipeline="CUSTOM", shader_name="Unlit/CurvedUnlit"),
            SimpleNamespace(pipeline="BUILTIN", shader_name="Standard"),
        ]
        assert _detect_unlit_game(results) is True  # 3/4 = 75% > 70%

    def test_mostly_lit_not_detected(self) -> None:
        from modules.conversion_helpers import _detect_unlit_game
        from types import SimpleNamespace

        results = [
            SimpleNamespace(pipeline="BUILTIN", shader_name="Standard"),
            SimpleNamespace(pipeline="BUILTIN", shader_name="Standard"),
            SimpleNamespace(pipeline="CUSTOM", shader_name="Unlit/Texture"),
        ]
        assert _detect_unlit_game(results) is False  # 1/3 = 33% < 70%

    def test_empty_not_detected(self) -> None:
        from modules.conversion_helpers import _detect_unlit_game
        assert _detect_unlit_game([]) is False
        assert _detect_unlit_game(None) is False


# ── Camera and Skybox in rbxl output ─────────────────────────────────


class TestCameraInRbxl:
    def test_camera_written_to_workspace(self, tmp_path: Path) -> None:
        from modules.rbxl_writer import RbxPartEntry, RbxCameraConfig, write_rbxl

        cam = RbxCameraConfig(
            position=(5.0, 10.0, -15.0),
            field_of_view=80.0,
        )
        rbxl = tmp_path / "cam.rbxl"
        result = write_rbxl([], [], rbxl, camera=cam)
        content = rbxl.read_text()
        assert "Camera" in content
        assert "FieldOfView" in content

    def test_skybox_written_to_lighting(self, tmp_path: Path) -> None:
        from modules.rbxl_writer import RbxPartEntry, RbxSkyboxConfig, write_rbxl

        sky = RbxSkyboxConfig(front="/tex/front.png", back="/tex/back.png")
        rbxl = tmp_path / "sky.rbxl"
        result = write_rbxl([], [], rbxl, skybox=sky)
        content = rbxl.read_text()
        assert "Sky" in content
        assert "SkyboxFt" in content


# ── Scene parser Camera CID ──────────────────────────────────────────


class TestSceneParserCamera:
    def test_camera_component_parsed(self, tmp_path: Path) -> None:
        from modules.scene_parser import parse_scene

        scene_file = tmp_path / "test.unity"
        scene_file.write_text(
            "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!1 &100\nGameObject:\n  m_Name: MainCam\n  m_IsActive: 1\n"
            "  m_Layer: 0\n  m_TagString: MainCamera\n"
            "--- !u!4 &200\nTransform:\n  m_GameObject: {fileID: 100}\n"
            "  m_LocalPosition: {x: 0, y: 5, z: -10}\n"
            "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
            "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
            "  m_Father: {fileID: 0}\n  m_Children: []\n"
            "--- !u!20 &300\nCamera:\n  m_GameObject: {fileID: 100}\n"
            "  field of view: 60\n  near clip plane: 0.3\n  far clip plane: 1000\n",
            encoding="utf-8",
        )
        result = parse_scene(scene_file)
        assert len(result.roots) == 1
        cam_comps = [c for c in result.roots[0].components if c.component_type == "Camera"]
        assert len(cam_comps) == 1


# ── Texture processing: detail/height operations ─────────────────────


class TestTextureProcessingDetailOps:
    """Integration tests for composite_detail, blend_normal_detail, heightmap_to_normal."""

    def _make_rgb_image(self, path: Path, color: tuple[int, int, int], size: int = 8) -> Path:
        from PIL import Image
        img = Image.new("RGB", (size, size), color)
        img.save(path, "PNG")
        return path

    def _make_grayscale_image(self, path: Path, value: int, size: int = 8) -> Path:
        from PIL import Image
        img = Image.new("L", (size, size), value)
        img.save(path, "PNG")
        return path

    def test_composite_detail_produces_output(self, tmp_path: Path) -> None:
        base = self._make_rgb_image(tmp_path / "base.png", (200, 100, 50))
        detail = self._make_rgb_image(tmp_path / "detail.png", (128, 128, 128))  # neutral grey
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "composite_detail", detail, "result.png",
            params={"base_path": str(base), "mask_path": "", "detail_tiling_x": 1, "detail_tiling_y": 1},
        )]
        result = _process_textures(ops, out_dir)
        assert len(result) == 1
        assert (out_dir / "result.png").exists()

    def test_composite_detail_neutral_grey_preserves_base(self, tmp_path: Path) -> None:
        """Neutral grey (128,128,128) detail should roughly preserve the base color."""
        from PIL import Image
        import numpy as np
        base = self._make_rgb_image(tmp_path / "base.png", (200, 100, 50))
        detail = self._make_rgb_image(tmp_path / "detail.png", (128, 128, 128))
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "composite_detail", detail, "result.png",
            params={"base_path": str(base), "mask_path": "", "detail_tiling_x": 1, "detail_tiling_y": 1},
        )]
        _process_textures(ops, out_dir)
        result = np.array(Image.open(out_dir / "result.png"))
        # With neutral grey overlay, result ≈ base (within rounding)
        expected = np.array(Image.open(base))
        assert np.allclose(result, expected, atol=5)

    def test_composite_detail_with_tiling(self, tmp_path: Path) -> None:
        from PIL import Image
        base = self._make_rgb_image(tmp_path / "base.png", (200, 100, 50))
        detail = self._make_rgb_image(tmp_path / "detail.png", (128, 128, 128), size=4)
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "composite_detail", detail, "result.png",
            params={"base_path": str(base), "mask_path": "", "detail_tiling_x": 2, "detail_tiling_y": 2},
        )]
        result = _process_textures(ops, out_dir)
        assert len(result) == 1

    def test_blend_normal_detail_produces_output(self, tmp_path: Path) -> None:
        # Flat normal map: (128, 128, 255) = pointing straight up
        base = self._make_rgb_image(tmp_path / "base.png", (128, 128, 255))
        detail = self._make_rgb_image(tmp_path / "detail.png", (128, 128, 255))
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "blend_normal_detail", detail, "result.png",
            params={"base_path": str(base), "mask_path": "", "detail_tiling_x": 1,
                    "detail_tiling_y": 1, "detail_normal_scale": 1.0},
        )]
        result = _process_textures(ops, out_dir)
        assert len(result) == 1

    def test_blend_normal_flat_detail_preserves_base(self, tmp_path: Path) -> None:
        """Flat detail normal (128,128,255) should preserve the base normal."""
        from PIL import Image
        import numpy as np
        base = self._make_rgb_image(tmp_path / "base.png", (128, 128, 255))
        detail = self._make_rgb_image(tmp_path / "detail.png", (128, 128, 255))
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "blend_normal_detail", detail, "result.png",
            params={"base_path": str(base), "mask_path": "", "detail_tiling_x": 1,
                    "detail_tiling_y": 1, "detail_normal_scale": 1.0},
        )]
        _process_textures(ops, out_dir)
        result = np.array(Image.open(out_dir / "result.png"))
        # Flat + flat should still be flat (128, 128, 255) ± rounding
        assert np.allclose(result[..., 0], 128, atol=2)
        assert np.allclose(result[..., 1], 128, atol=2)
        assert result[..., 2].mean() > 200  # Z should remain dominant

    def test_heightmap_to_normal_produces_output(self, tmp_path: Path) -> None:
        height = self._make_grayscale_image(tmp_path / "height.png", 128)
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "heightmap_to_normal", height, "normal.png",
            params={"strength": 0.05},
        )]
        result = _process_textures(ops, out_dir)
        assert len(result) == 1
        assert (out_dir / "normal.png").exists()

    def test_heightmap_flat_produces_flat_normal(self, tmp_path: Path) -> None:
        """Flat heightmap (uniform value) should produce a flat normal map."""
        from PIL import Image
        import numpy as np
        height = self._make_grayscale_image(tmp_path / "height.png", 128)
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "heightmap_to_normal", height, "normal.png",
            params={"strength": 0.05},
        )]
        _process_textures(ops, out_dir)
        result = np.array(Image.open(out_dir / "normal.png"))
        # Flat heightmap → Sobel gradients are 0 → normal is (0,0,1) → (128,128,255)
        assert np.allclose(result[..., 0], 128, atol=2)
        assert np.allclose(result[..., 1], 128, atol=2)
        assert np.allclose(result[..., 2], 255, atol=2)

    def test_heightmap_blended_into_existing_normal(self, tmp_path: Path) -> None:
        base_normal = self._make_rgb_image(tmp_path / "base_normal.png", (128, 128, 255))
        height = self._make_grayscale_image(tmp_path / "height.png", 128)
        out_dir = tmp_path / "out"
        ops = [TextureOperation(
            "heightmap_to_normal", height, "normal.png",
            params={"strength": 0.05, "base_normal_path": str(base_normal)},
        )]
        result = _process_textures(ops, out_dir)
        assert len(result) == 1
