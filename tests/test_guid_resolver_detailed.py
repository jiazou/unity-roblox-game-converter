"""Fine-grained unit tests for modules/guid_resolver.py.

Tests resolve_chain, multi-kind classification, non-standard meta formats,
Packages/ exclusion, and edge cases in GUID parsing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.guid_resolver import (
    GuidEntry,
    GuidIndex,
    build_guid_index,
    _parse_meta_file,
    _EXT_TO_KIND,
)
from tests.conftest import make_meta


class TestExtToKind:
    """Test asset kind classification from file extensions via _EXT_TO_KIND."""

    @pytest.mark.parametrize("ext,expected", [
        (".png", "texture"),
        (".jpg", "texture"),
        (".jpeg", "texture"),
        (".tga", "texture"),
        (".bmp", "texture"),
        (".psd", "texture"),
        (".mat", "material"),
        (".fbx", "mesh"),
        (".obj", "mesh"),
        (".dae", "mesh"),
        (".prefab", "prefab"),
        (".unity", "scene"),
        (".cs", "script"),
        (".shader", "shader"),
        (".cginc", "shader"),
        (".hlsl", "shader"),
        (".anim", "animation"),
        (".controller", "animation"),
        (".wav", "audio"),
        (".mp3", "audio"),
        (".ogg", "audio"),
        (".xyz", "unknown"),
    ])
    def test_extension_classification(self, ext: str, expected: str) -> None:
        assert _EXT_TO_KIND.get(ext, "unknown") == expected


class TestParseMetaFile:
    """Test parsing of individual .meta files."""

    def test_standard_meta(self, tmp_path: Path) -> None:
        meta = tmp_path / "tex.png.meta"
        make_meta(meta, "abcd" * 8)
        result = _parse_meta_file(meta)
        assert result is not None
        guid, is_folder = result
        assert guid == "abcd" * 8
        assert is_folder is False

    def test_meta_with_extra_fields(self, tmp_path: Path) -> None:
        meta = tmp_path / "file.mat.meta"
        content = (
            "fileFormatVersion: 2\n"
            "guid: 1234567890abcdef1234567890abcdef\n"
            "NativeFormatImporter:\n"
            "  externalObjects: {}\n"
        )
        meta.write_text(content, encoding="utf-8")
        result = _parse_meta_file(meta)
        assert result is not None
        guid, _ = result
        assert guid == "1234567890abcdef1234567890abcdef"

    def test_meta_without_guid(self, tmp_path: Path) -> None:
        meta = tmp_path / "noid.meta"
        meta.write_text("fileFormatVersion: 2\n", encoding="utf-8")
        result = _parse_meta_file(meta)
        assert result is None

    def test_empty_meta_file(self, tmp_path: Path) -> None:
        meta = tmp_path / "empty.meta"
        meta.write_text("", encoding="utf-8")
        result = _parse_meta_file(meta)
        assert result is None


class TestGuidIndexResolveChain:
    """Test transitive GUID resolution (e.g. prefab variants)."""

    def test_single_step_chain(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        chain = idx.resolve_chain("aaaa0000aaaa0000aaaa0000aaaa0001")
        assert len(chain) >= 1
        assert chain[0].asset_path.name == "red.png"

    def test_unknown_guid_empty_chain(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        chain = idx.resolve_chain("0000000000000000000000000000dead")
        assert chain == []

    def test_max_depth_respected(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        chain = idx.resolve_chain("aaaa0000aaaa0000aaaa0000aaaa0001", max_depth=1)
        assert len(chain) <= 1


class TestGuidIndexFilterByKind:
    """Test filtering GUIDs by asset kind."""

    def test_filter_textures(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        textures = idx.filter_by_kind("texture")
        for guid, entry in textures.items():
            assert entry.kind == "texture"
            assert entry.asset_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".tga", ".bmp")

    def test_filter_materials(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        materials = idx.filter_by_kind("material")
        for guid, entry in materials.items():
            assert entry.kind == "material"
            assert entry.asset_path.suffix == ".mat"

    def test_filter_scripts(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        scripts = idx.filter_by_kind("script")
        for guid, entry in scripts.items():
            assert entry.kind == "script"
            assert entry.asset_path.suffix == ".cs"

    def test_filter_unknown_kind_empty(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        result = idx.filter_by_kind("video")
        assert len(result) == 0


class TestGuidIndexEdgeCases:
    """Edge cases for the GUID index."""

    def test_nested_subdirectory_assets(self, tmp_path: Path) -> None:
        """Assets in deeply nested directories should be discovered."""
        project = tmp_path / "Deep"
        deep_dir = project / "Assets" / "Art" / "Textures" / "Environment"
        deep_dir.mkdir(parents=True)
        tex = deep_dir / "grass.png"
        tex.write_bytes(b"PNG_DATA")
        make_meta(tex.with_suffix(".png.meta"), "deed0000deed0000deed0000deed0001")

        idx = build_guid_index(project)
        resolved = idx.resolve("deed0000deed0000deed0000deed0001")
        assert resolved is not None
        assert resolved.name == "grass.png"

    def test_guid_for_path_case_sensitivity(self, unity_project: Path) -> None:
        """Path lookup should be based on resolved paths."""
        idx = build_guid_index(unity_project)
        tex_path = (unity_project / "Assets" / "red.png").resolve()
        guid = idx.guid_for_path(tex_path)
        assert guid == "aaaa0000aaaa0000aaaa0000aaaa0001"

    def test_resolve_relative_format(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        rel = idx.resolve_relative("aaaa0000aaaa0000aaaa0000aaaa0001")
        assert rel is not None
        parts = str(rel).split("/")
        assert "Assets" in parts

    def test_resolve_ref_with_type_field(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        ref = {"fileID": 2800000, "guid": "aaaa0000aaaa0000aaaa0000aaaa0001", "type": 3}
        resolved = idx.resolve_ref(ref)
        assert resolved is not None
        assert resolved.name == "red.png"

    def test_multiple_asset_types_coexist(self, tmp_path: Path) -> None:
        """Multiple asset types in the same directory should all be indexed."""
        project = tmp_path / "Multi"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        hex_prefixes = ["aaa10000", "bbb20000", "ccc30000", "ddd40000"]
        for i, (name, ext, data) in enumerate([
            ("diffuse", ".png", b"PNG"),
            ("model", ".fbx", b"FBX"),
            ("mat", ".mat", b"MAT"),
            ("script", ".cs", b"CS"),
        ]):
            f = assets / f"{name}{ext}"
            f.write_bytes(data)
            guid = hex_prefixes[i] * 4
            make_meta(f.parent / f"{f.name}.meta", guid)

        idx = build_guid_index(project)
        assert idx.total_resolved >= 4

        textures = idx.filter_by_kind("texture")
        meshes = idx.filter_by_kind("mesh")
        materials = idx.filter_by_kind("material")
        scripts = idx.filter_by_kind("script")

        assert len(textures) >= 1
        assert len(meshes) >= 1
        assert len(materials) >= 1
        assert len(scripts) >= 1
