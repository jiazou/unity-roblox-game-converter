"""Black-box tests for modules/guid_resolver.py."""

from pathlib import Path

import pytest

from modules.guid_resolver import GuidIndex, build_guid_index
from tests.conftest import make_meta


class TestBuildGuidIndex:
    """Tests for the build_guid_index() public API."""

    def test_returns_guid_index(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        assert isinstance(idx, GuidIndex)
        assert idx.project_root == unity_project.resolve()

    def test_resolves_all_meta_files(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        assert idx.total_meta_files > 0
        assert idx.total_resolved > 0

    def test_resolve_by_guid(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        # The red.png texture has guid "aaaa0000aaaa0000aaaa0000aaaa0001"
        path = idx.resolve("aaaa0000aaaa0000aaaa0000aaaa0001")
        assert path is not None
        assert path.name == "red.png"

    def test_resolve_returns_none_for_unknown(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        assert idx.resolve("0000000000000000000000000000dead") is None

    def test_resolve_kind(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        assert idx.resolve_kind("aaaa0000aaaa0000aaaa0000aaaa0001") == "texture"
        assert idx.resolve_kind("eeee0000eeee0000eeee0000eeee0001") == "material"
        assert idx.resolve_kind("dddd0000dddd0000dddd0000dddd0001") == "mesh"

    def test_resolve_relative(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        rel = idx.resolve_relative("aaaa0000aaaa0000aaaa0000aaaa0001")
        assert rel is not None
        assert "Assets" in str(rel)
        assert "red.png" in str(rel)

    def test_guid_for_path(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        tex_path = (unity_project / "Assets" / "red.png").resolve()
        guid = idx.guid_for_path(tex_path)
        assert guid == "aaaa0000aaaa0000aaaa0000aaaa0001"

    def test_guid_for_path_unknown(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        assert idx.guid_for_path(Path("/nonexistent/file.png")) is None

    def test_resolve_ref_dict(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        ref = {"fileID": 2800000, "guid": "aaaa0000aaaa0000aaaa0000aaaa0001", "type": 3}
        path = idx.resolve_ref(ref)
        assert path is not None
        assert path.name == "red.png"

    def test_resolve_ref_empty_guid(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        ref = {"fileID": 0, "guid": "", "type": 0}
        assert idx.resolve_ref(ref) is None

    def test_resolve_ref_zero_guid(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        ref = {"fileID": 0, "guid": "0" * 32, "type": 0}
        assert idx.resolve_ref(ref) is None

    def test_filter_by_kind(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        textures = idx.filter_by_kind("texture")
        assert len(textures) >= 3
        for guid, entry in textures.items():
            assert entry.kind == "texture"

    def test_filter_by_kind_mesh(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        meshes = idx.filter_by_kind("mesh")
        assert len(meshes) >= 1

    def test_missing_assets_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Assets"):
            build_guid_index(tmp_path / "nonexistent")

    def test_orphan_metas_detected(self, unity_project: Path) -> None:
        # Create an orphan .meta (no corresponding asset)
        orphan = unity_project / "Assets" / "ghost.png.meta"
        make_meta(orphan, "dead0000dead0000dead0000dead0000")
        idx = build_guid_index(unity_project)
        assert len(idx.orphan_metas) >= 1

    def test_duplicate_guids_detected(self, unity_project: Path) -> None:
        # Create a second meta with the same GUID as red.png
        dup = unity_project / "Assets" / "duplicate.png"
        dup.write_bytes(b"fake")
        make_meta(dup.with_suffix(".png.meta"), "aaaa0000aaaa0000aaaa0000aaaa0001")
        idx = build_guid_index(unity_project)
        assert "aaaa0000aaaa0000aaaa0000aaaa0001" in idx.duplicate_guids

    def test_empty_assets_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "Empty"
        (project / "Assets").mkdir(parents=True)
        idx = build_guid_index(project)
        assert idx.total_resolved == 0
        assert idx.total_meta_files == 0

    def test_folder_meta_classified(self, unity_project: Path) -> None:
        folder = unity_project / "Assets" / "Subfolder"
        folder.mkdir()
        make_meta(
            unity_project / "Assets" / "Subfolder.meta",
            "aaaa0000aaaa0000aaaa0000aaaa9999",
            is_folder=True,
        )
        idx = build_guid_index(unity_project)
        entry = idx.guid_to_entry.get("aaaa0000aaaa0000aaaa0000aaaa9999")
        assert entry is not None
        assert entry.is_directory is True
        assert entry.kind == "directory"

    def test_prefab_guid_resolvable(self, unity_project: Path) -> None:
        idx = build_guid_index(unity_project)
        entry = idx.guid_to_entry.get("ffff0000ffff0000ffff0000ffff0001")
        assert entry is not None
        assert entry.kind == "prefab"
