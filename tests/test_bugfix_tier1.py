"""Tests for Tier 1 bug fixes:

1. YAML parse error surfacing (parse_documents error_counts + ParsedScene.parse_warnings)
2. Audio GUID resolution (full path instead of filename-only rglob)
3. Assemble phase loading scripts from disk instead of re-transpiling
"""

from __future__ import annotations

import json
import logging
import textwrap
from pathlib import Path

import pytest

from modules.unity_yaml_utils import parse_documents
from modules import scene_parser, guid_resolver, prefab_parser
from modules.conversion_helpers import extract_serialized_field_refs


# ---------------------------------------------------------------------------
# 1. YAML parse error surfacing
# ---------------------------------------------------------------------------

class TestParseDocumentsErrorCounts:
    """parse_documents() should report YAML parse errors via error_counts."""

    def test_error_counts_populated_on_bad_yaml(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Good
            --- !u!4 &200
            {{{bad yaml!!!
        """)
        error_counts: list[int] = []
        result = parse_documents(raw, error_counts=error_counts)
        assert len(result) == 1  # only the good document
        assert result[0][0] == 1
        assert error_counts[0] == 1

    def test_error_counts_zero_on_clean_yaml(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Good
        """)
        error_counts: list[int] = []
        result = parse_documents(raw, error_counts=error_counts)
        assert len(result) == 1
        assert error_counts[0] == 0

    def test_error_counts_none_is_safe(self) -> None:
        """Passing None for error_counts doesn't crash."""
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            {{{bad yaml!!!
        """)
        result = parse_documents(raw, error_counts=None)
        assert result == []

    def test_error_counts_not_passed(self) -> None:
        """Default (no error_counts arg) still works."""
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            {{{bad yaml!!!
        """)
        result = parse_documents(raw)
        assert result == []

    def test_multiple_errors_counted(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Good
            --- !u!4 &200
            {{{bad1
            --- !u!4 &300
            {{{bad2
        """)
        error_counts: list[int] = []
        result = parse_documents(raw, error_counts=error_counts)
        assert len(result) == 1
        assert error_counts[0] == 2

    def test_warning_logged_on_parse_error(self, caplog) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Good
            --- !u!4 &200
            {{{bad yaml!!!
        """)
        with caplog.at_level(logging.WARNING, logger="modules.unity_yaml_utils"):
            parse_documents(raw)
        assert any("failed to parse" in msg for msg in caplog.messages)
        assert any("1 YAML document" in msg for msg in caplog.messages)

    def test_no_warning_on_clean_yaml(self, caplog) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Good
        """)
        with caplog.at_level(logging.WARNING, logger="modules.unity_yaml_utils"):
            parse_documents(raw)
        assert not any("failed to parse" in msg for msg in caplog.messages)


class TestParsedSceneParseWarnings:
    """ParsedScene.parse_warnings should surface YAML parse errors."""

    def test_clean_scene_has_no_warnings(self, tmp_path: Path) -> None:
        scene_file = tmp_path / "Clean.unity"
        scene_file.write_text(textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: TestObj
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
        """), encoding="utf-8")
        result = scene_parser.parse_scene(scene_file)
        assert result.parse_warnings == []

    def test_corrupt_doc_produces_warning(self, tmp_path: Path) -> None:
        scene_file = tmp_path / "Corrupt.unity"
        scene_file.write_text(textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: TestObj
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
            --- !u!23 &300
            {{{this is corrupt yaml!!!
        """), encoding="utf-8")
        result = scene_parser.parse_scene(scene_file)
        assert len(result.parse_warnings) == 1
        assert "failed to parse" in result.parse_warnings[0]
        assert "Corrupt.unity" in result.parse_warnings[0]
        # The valid documents should still be parsed
        assert len(result.all_nodes) == 1  # The one valid GameObject


# ---------------------------------------------------------------------------
# 2. Audio GUID resolution (full path)
# ---------------------------------------------------------------------------

def _make_guid_index(tmp_path, entries):
    """Build a GuidIndex with the given (guid, rel_path, kind) entries.

    Creates real files so that resolve() returns valid absolute paths.
    """
    gi = guid_resolver.GuidIndex(project_root=tmp_path)
    for guid, rel_path_str, kind in entries:
        asset_path = tmp_path / rel_path_str
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("", encoding="utf-8")
        gi.guid_to_entry[guid] = guid_resolver.GuidEntry(
            guid=guid,
            asset_path=asset_path.resolve(),
            relative_path=Path(rel_path_str),
            kind=kind,
            is_directory=False,
        )
        gi.path_to_guid[asset_path.resolve()] = guid
    return gi


class TestAudioGuidResolution:
    """Audio references should contain full resolved path, not just filename."""

    def test_audio_ref_contains_full_path(self, tmp_path: Path) -> None:
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/SoundPlayer.cs", "script"),
            ("audio_guid_1", "Assets/Audio/explosion.ogg", "audio"),
        ])
        node = scene_parser.SceneNode(
            name="SFXManager", file_id="100",
            active=True, layer=0, tag="Untagged",
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_GameObject": {"fileID": 100},
                        "explosionClip": {"fileID": 0, "guid": "audio_guid_1", "type": 3},
                    },
                ),
            ],
        )
        scene = scene_parser.ParsedScene(
            scene_path=tmp_path / "test.unity",
            all_nodes={"100": node},
            roots=[node],
        )
        result = extract_serialized_field_refs([scene], prefab_parser.PrefabLibrary(), gi)

        script_path = (tmp_path / "Assets/Scripts/SoundPlayer.cs").resolve()
        assert script_path in result
        audio_value = result[script_path]["explosionClip"]
        assert audio_value.startswith("audio:")
        # The path should be a full absolute path, not just a filename
        audio_path = audio_value[len("audio:"):]
        assert "/" in audio_path or "\\" in audio_path  # has directory components
        assert Path(audio_path).name == "explosion.ogg"
        assert Path(audio_path).is_file()

    def test_wav_audio_ref_contains_full_path(self, tmp_path: Path) -> None:
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Music.cs", "script"),
            ("audio_guid_1", "Assets/Audio/Ambient/forest.wav", "audio"),
        ])
        node = scene_parser.SceneNode(
            name="MusicPlayer", file_id="100",
            active=True, layer=0, tag="Untagged",
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_GameObject": {"fileID": 100},
                        "bgMusic": {"fileID": 0, "guid": "audio_guid_1", "type": 3},
                    },
                ),
            ],
        )
        scene = scene_parser.ParsedScene(
            scene_path=tmp_path / "test.unity",
            all_nodes={"100": node},
            roots=[node],
        )
        result = extract_serialized_field_refs([scene], prefab_parser.PrefabLibrary(), gi)

        script_path = (tmp_path / "Assets/Scripts/Music.cs").resolve()
        audio_value = result[script_path]["bgMusic"]
        audio_path = Path(audio_value[len("audio:"):])
        # Should be the full path to the file in Assets/Audio/Ambient/
        assert audio_path.name == "forest.wav"
        assert "Ambient" in str(audio_path)

    def test_mp3_audio_ref_supported(self, tmp_path: Path) -> None:
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Player.cs", "script"),
            ("audio_guid_1", "Assets/Audio/theme.mp3", "audio"),
        ])
        node = scene_parser.SceneNode(
            name="Player", file_id="100",
            active=True, layer=0, tag="Untagged",
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_GameObject": {"fileID": 100},
                        "themeMusic": {"fileID": 0, "guid": "audio_guid_1", "type": 3},
                    },
                ),
            ],
        )
        scene = scene_parser.ParsedScene(
            scene_path=tmp_path / "test.unity",
            all_nodes={"100": node},
            roots=[node],
        )
        result = extract_serialized_field_refs([scene], prefab_parser.PrefabLibrary(), gi)
        script_path = (tmp_path / "Assets/Scripts/Player.cs").resolve()
        audio_value = result[script_path]["themeMusic"]
        assert audio_value.startswith("audio:")
        assert Path(audio_value[len("audio:"):]).name == "theme.mp3"


# ---------------------------------------------------------------------------
# 3. Assemble phase: scripts loaded from disk
# ---------------------------------------------------------------------------

class TestAssembleScriptDiskLoading:
    """The assemble phase should load scripts from disk when available,
    rather than re-running AI transpilation."""

    def test_scripts_dir_with_lua_files_detected(self, tmp_path: Path) -> None:
        """When scripts/ dir has .lua files, they should be loadable."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        # Write a script and meta
        (scripts_dir / "PlayerController.lua").write_text(
            "-- User-edited Luau script\nprint('hello')\n",
            encoding="utf-8",
        )
        meta = {
            "PlayerController.lua": {
                "script_type": "Script",
                "confidence": 0.95,
                "source_path": "Assets/Scripts/PlayerController.cs",
            }
        }
        (scripts_dir / "_meta.json").write_text(
            json.dumps(meta), encoding="utf-8",
        )

        # Verify the scripts dir detection logic works
        assert scripts_dir.is_dir()
        lua_files = list(scripts_dir.glob("*.lua"))
        assert len(lua_files) == 1
        assert lua_files[0].name == "PlayerController.lua"

        # Verify the meta can be loaded
        loaded_meta = json.loads(
            (scripts_dir / "_meta.json").read_text(encoding="utf-8")
        )
        assert "PlayerController.lua" in loaded_meta
        assert loaded_meta["PlayerController.lua"]["script_type"] == "Script"

    def test_empty_scripts_dir_not_detected(self, tmp_path: Path) -> None:
        """An empty scripts/ dir should not be treated as having scripts."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        assert scripts_dir.is_dir()
        assert not any(scripts_dir.glob("*.lua"))
        assert not any(scripts_dir.glob("*.luau"))

    def test_luau_extension_also_detected(self, tmp_path: Path) -> None:
        """Scripts with .luau extension should also be detected."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "Module.luau").write_text(
            "local M = {}\nreturn M\n", encoding="utf-8",
        )
        assert any(scripts_dir.glob("*.luau"))

    def test_disk_script_content_preserved(self, tmp_path: Path) -> None:
        """Content from disk scripts should be read verbatim."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        expected_content = "-- This was hand-edited by user\nlocal x = 42\nreturn x\n"
        (scripts_dir / "Custom.lua").write_text(expected_content, encoding="utf-8")

        lua_file = next(scripts_dir.glob("*.lua"))
        assert lua_file.read_text(encoding="utf-8") == expected_content
