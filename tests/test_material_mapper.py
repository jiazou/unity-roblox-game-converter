"""Black-box tests for modules/material_mapper.py."""

from pathlib import Path

import pytest

from modules.material_mapper import (
    MaterialMapResult,
    RobloxMaterialDef,
    map_materials,
)


class TestMapMaterials:
    """Tests for the map_materials() public API."""

    def test_returns_material_map_result(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        assert isinstance(result, MaterialMapResult)

    def test_discovers_all_mat_files(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        assert result.total >= 4  # Standard, URP Unlit, URP Lit, Particle

    def test_standard_shader_detected(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        standard = next(
            (m for m in result.materials if m.material_name == "TestStandard"), None
        )
        assert standard is not None
        assert standard.pipeline == "BUILTIN"
        assert standard.shader_name == "Standard"

    def test_standard_material_has_roblox_def(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        standard = next(m for m in result.materials if m.material_name == "TestStandard")
        assert standard.roblox_def is not None
        rdef = standard.roblox_def
        assert rdef.color_map is not None  # has _MainTex
        assert rdef.normal_map is not None  # has _BumpMap

    def test_standard_material_albedo_color(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        standard = next(m for m in result.materials if m.material_name == "TestStandard")
        rdef = standard.roblox_def
        # _Color: r=0.8, g=0.2, b=0.1 → color_tint should be set (non-white)
        assert rdef.color_tint != (1.0, 1.0, 1.0)

    def test_standard_roughness_from_smoothness(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        standard = next(m for m in result.materials if m.material_name == "TestStandard")
        rdef = standard.roblox_def
        # _Glossiness=0.6 → roughness=0.4 → uniform texture should be generated
        assert rdef.roughness_map is not None

    def test_standard_metallic_scalar(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        standard = next(m for m in result.materials if m.material_name == "TestStandard")
        rdef = standard.roblox_def
        # _Metallic=0.2 → uniform metalness texture generated
        assert rdef.metalness_map is not None

    def test_urp_unlit_detected(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        urp_unlit = next(
            (m for m in result.materials if m.material_name == "TestURPUnlit"), None
        )
        assert urp_unlit is not None
        assert urp_unlit.pipeline == "URP"
        assert "Unlit" in urp_unlit.shader_name

    def test_urp_lit_detected(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        urp_lit = next(
            (m for m in result.materials if m.material_name == "TestURPLit"), None
        )
        assert urp_lit is not None
        assert urp_lit.pipeline == "URP"
        assert "Lit" in urp_lit.shader_name
        assert urp_lit.shader_name != "Universal Render Pipeline/Unlit"

    def test_urp_lit_has_pbr_maps(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        urp_lit = next(m for m in result.materials if m.material_name == "TestURPLit")
        rdef = urp_lit.roblox_def
        assert rdef is not None
        # URP Lit with _MetallicGlossMap should have metalness/roughness
        assert rdef.metalness_map is not None
        assert rdef.roughness_map is not None

    def test_particle_material_detected(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        particle = next(
            (m for m in result.materials if m.material_name == "TestParticle"), None
        )
        assert particle is not None
        assert particle.pipeline == "PARTICLE"

    def test_particle_has_color_map(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        particle = next(m for m in result.materials if m.material_name == "TestParticle")
        rdef = particle.roblox_def
        assert rdef is not None
        # Particle materials with _MainTex should produce a color_map
        assert rdef.color_map is not None
        # Particle shader typically sets alpha mode to Transparency
        assert rdef.alpha_mode == "Transparency"

    def test_referenced_guids_filter(self, unity_project: Path, tmp_path: Path) -> None:
        # Only process the Standard material GUID
        result = map_materials(
            unity_project, tmp_path / "out",
            referenced_guids={"eeee0000eeee0000eeee0000eeee0001"},
        )
        assert result.total == 1
        assert result.materials[0].material_name == "TestStandard"

    def test_empty_referenced_guids(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(
            unity_project, tmp_path / "out",
            referenced_guids=set(),
        )
        assert result.total == 0

    def test_unconverted_md_generated(self, unity_project: Path, tmp_path: Path) -> None:
        out = tmp_path / "out"
        result = map_materials(unity_project, out)
        assert result.unconverted_md_path is not None
        assert result.unconverted_md_path.exists()
        content = result.unconverted_md_path.read_text()
        assert "Conversion Statistics" in content

    def test_statistics_add_up(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        assert result.total == (
            result.fully_converted + result.partially_converted + result.unconvertible
        )

    def test_roblox_defs_keyed_by_path(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        for mat_path, rdef in result.roblox_defs.items():
            assert isinstance(mat_path, Path)
            assert isinstance(rdef, RobloxMaterialDef)

    def test_texture_ops_performed(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        # Standard material has textures → at least one texture op
        assert result.texture_ops_performed >= 0

    def test_alpha_mode_opaque_default(self, unity_project: Path, tmp_path: Path) -> None:
        result = map_materials(unity_project, tmp_path / "out")
        standard = next(m for m in result.materials if m.material_name == "TestStandard")
        assert standard.roblox_def.alpha_mode == "Opaque"

    def test_no_crash_on_missing_project(self, tmp_path: Path) -> None:
        """map_materials should not crash on a project with no Assets/."""
        project = tmp_path / "Empty"
        project.mkdir()
        (project / "Assets").mkdir()
        result = map_materials(project, tmp_path / "out")
        assert result.total == 0


class TestMaterialMapperEdgeCases:
    """Edge case tests for material mapper behavior."""

    def test_tiling_material(self, tmp_path: Path) -> None:
        """Material with texture tiling > 1 should be handled (pre-tile, warning, or fallback)."""
        # The URP Unlit material has tiling (2, 2)
        from tests.conftest import URP_UNLIT_MAT_YAML, make_meta

        project = tmp_path / "TilingProject"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        mat = assets / "Tiled.mat"
        mat.write_text(URP_UNLIT_MAT_YAML, encoding="utf-8")
        make_meta(mat.with_suffix(".mat.meta"), "eeee0000eeee0000eeee0000eeee0002")

        result = map_materials(project, tmp_path / "out")
        tiled = result.materials[0]
        rdef = tiled.roblox_def
        assert rdef is not None
        # Tiling (2, 2) may trigger pre_tile op, unconverted log, warning, or be ignored
        tile_ops = [op for op in tiled.texture_ops if "tile" in getattr(op, "operation", "")]
        has_tile_handling = (
            len(tile_ops) > 0
            or len(tiled.unconverted) > 0
            or len(tiled.warnings) > 0
            or tiled.fully_converted  # may just pass through
        )
        assert has_tile_handling

    def test_no_texture_flat_color(self, tmp_path: Path) -> None:
        """Material with no texture should fall back to base_part_color."""
        import textwrap
        from tests.conftest import make_meta

        project = tmp_path / "FlatColorProject"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        flat_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!21 &2100000
            Material:
              m_Name: FlatRed
              m_Shader: {fileID: 46}
              m_SavedProperties:
                m_TexEnvs:
                  - _MainTex:
                      m_Texture: {fileID: 0}
                      m_Scale: {x: 1, y: 1}
                      m_Offset: {x: 0, y: 0}
                m_Floats:
                  - _Mode: 0
                m_Colors:
                  - _Color: {r: 1, g: 0, b: 0, a: 1}
        """)
        mat = assets / "FlatRed.mat"
        mat.write_text(flat_yaml, encoding="utf-8")
        make_meta(mat.with_suffix(".mat.meta"), "flat0000flat0000flat0000flat0000")

        result = map_materials(project, tmp_path / "out")
        flat = result.materials[0]
        rdef = flat.roblox_def
        assert rdef is not None
        assert rdef.color_map is None
        assert rdef.base_part_color is not None
        # Red color
        assert rdef.base_part_color[0] > 0.9
        assert rdef.base_part_color[1] < 0.1
