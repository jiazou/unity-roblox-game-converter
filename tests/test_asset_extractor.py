"""Black-box tests for modules/asset_extractor.py."""

from pathlib import Path

import pytest

from modules.asset_extractor import AssetManifest, extract_assets


class TestExtractAssets:
    """Tests for the extract_assets() public API."""

    def test_discovers_all_assets(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        # At minimum: 3 textures + 4 mats + 1 mesh = 8 assets
        assert manifest.assets, "No assets discovered"
        assert len(manifest.assets) >= 8

    def test_returns_asset_manifest_type(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        assert isinstance(manifest, AssetManifest)
        assert manifest.unity_project_path == unity_project.resolve()

    def test_classifies_textures(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        textures = manifest.by_kind.get("texture", [])
        assert len(textures) >= 3
        for t in textures:
            assert t.kind == "texture"
            assert t.path.suffix.lower() in (".png", ".jpg", ".jpeg", ".tga", ".bmp")

    def test_classifies_materials(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        materials = manifest.by_kind.get("material", [])
        assert len(materials) >= 4
        for m in materials:
            assert m.kind == "material"
            assert m.path.suffix == ".mat"

    def test_classifies_meshes(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        meshes = manifest.by_kind.get("mesh", [])
        assert len(meshes) >= 1
        assert meshes[0].kind == "mesh"

    def test_sha256_populated(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        for asset in manifest.assets:
            assert len(asset.sha256) == 64  # hex sha256

    def test_size_bytes_positive(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        for asset in manifest.assets:
            assert asset.size_bytes > 0

    def test_total_size_bytes_is_sum(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        assert manifest.total_size_bytes == sum(a.size_bytes for a in manifest.assets)

    def test_relative_path_populated(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        for asset in manifest.assets:
            assert "Assets" in str(asset.relative_path)

    def test_meta_path_resolved(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        textures = manifest.by_kind.get("texture", [])
        for t in textures:
            assert t.meta_path is not None, f"Meta not found for {t.path.name}"
            assert t.meta_path.exists()

    def test_supported_extensions_filter(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project, supported_extensions=[".png"])
        for asset in manifest.assets:
            assert asset.path.suffix.lower() == ".png"

    def test_missing_assets_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Assets"):
            extract_assets(tmp_path / "nonexistent")

    def test_empty_assets_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "EmptyProject"
        (project / "Assets").mkdir(parents=True)
        manifest = extract_assets(project)
        assert manifest.assets == []
        assert manifest.total_size_bytes == 0

    def test_dedup_map_populated(self, unity_project: Path) -> None:
        manifest = extract_assets(unity_project)
        assert len(manifest.by_sha256) > 0
        for sha, entry in manifest.by_sha256.items():
            assert len(sha) == 64
            assert entry.path.exists()
