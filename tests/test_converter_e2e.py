"""End-to-end integration test for the full conversion pipeline.

Creates a minimal Unity project fixture and runs the entire converter
pipeline through Click's test runner, verifying that the .rbxl file,
report JSON, and other outputs are produced correctly.
"""

from __future__ import annotations

import json
import struct
import textwrap
import zlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from converter import convert


def _make_1px_png(r: int, g: int, b: int) -> bytes:
    """Generate a minimal valid 1x1 PNG file."""
    raw_row = b"\x00" + bytes([r, g, b])
    compressed = zlib.compress(raw_row)

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def _make_meta(path: Path, guid: str) -> None:
    """Write a minimal Unity .meta file."""
    path.write_text(
        f"fileFormatVersion: 2\n"
        f"guid: {guid}\n"
        f"NativeFormatImporter:\n"
        f"  userData:\n",
        encoding="utf-8",
    )


@pytest.fixture
def full_unity_project(tmp_path: Path) -> Path:
    """Create a complete minimal Unity project with all asset types."""
    root = tmp_path / "FullProject"
    assets = root / "Assets"
    assets.mkdir(parents=True)

    # --- Textures ---
    tex = assets / "albedo.png"
    tex.write_bytes(_make_1px_png(200, 100, 50))
    _make_meta(tex.with_suffix(".png.meta"), "a000a000a000a000a000a000a000a001")

    normal = assets / "normal.png"
    normal.write_bytes(_make_1px_png(128, 128, 255))
    _make_meta(normal.with_suffix(".png.meta"), "a000a000a000a000a000a000a000a002")

    # --- Material (Standard shader) ---
    mat = assets / "Floor.mat"
    mat.write_text(textwrap.dedent("""\
        %YAML 1.1
        %TAG !u! tag:unity3d.com,2011:
        --- !u!21 &2100000
        Material:
          m_Name: Floor
          m_Shader: {fileID: 46}
          m_ShaderKeywords: ""
          m_SavedProperties:
            m_TexEnvs:
              - _MainTex:
                  m_Texture: {fileID: 2800000, guid: a000a000a000a000a000a000a000a001, type: 3}
                  m_Scale: {x: 1, y: 1}
                  m_Offset: {x: 0, y: 0}
              - _BumpMap:
                  m_Texture: {fileID: 2800000, guid: a000a000a000a000a000a000a000a002, type: 3}
                  m_Scale: {x: 1, y: 1}
                  m_Offset: {x: 0, y: 0}
            m_Floats:
              - _Metallic: 0.0
              - _Glossiness: 0.5
              - _BumpScale: 1
              - _Mode: 0
            m_Colors:
              - _Color: {r: 1, g: 1, b: 1, a: 1}
    """), encoding="utf-8")
    _make_meta(mat.with_suffix(".mat.meta"), "e000e000e000e000e000e000e000e001")

    # --- Mesh (simple OBJ) ---
    mesh = assets / "floor.obj"
    mesh.write_text(
        "v 0 0 0\nv 10 0 0\nv 10 0 10\nv 0 0 10\n"
        "f 1 2 3\nf 1 3 4\n",
        encoding="utf-8",
    )
    _make_meta(mesh.with_suffix(".obj.meta"), "d000d000d000d000d000d000d000d001")

    # --- C# Script ---
    script = assets / "GameManager.cs"
    script.write_text(textwrap.dedent("""\
        using UnityEngine;
        public class GameManager : MonoBehaviour {
            public float speed = 3.0f;
            void Start() {
                Debug.Log("Game started");
            }
            void Update() {
                transform.Translate(Vector3.forward * speed * Time.deltaTime);
            }
        }
    """), encoding="utf-8")
    _make_meta(script.with_suffix(".cs.meta"), "c000c000c000c000c000c000c000c001")

    # --- Scene ---
    scene = assets / "Main.unity"
    scene.write_text(textwrap.dedent("""\
        %YAML 1.1
        %TAG !u! tag:unity3d.com,2011:
        --- !u!1 &100
        GameObject:
          m_Name: FloorObject
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
        --- !u!33 &300
        MeshFilter:
          m_GameObject: {fileID: 100}
          m_Mesh: {fileID: 4300000, guid: d000d000d000d000d000d000d000d001, type: 3}
        --- !u!23 &400
        MeshRenderer:
          m_GameObject: {fileID: 100}
          m_Materials:
            - {fileID: 2100000, guid: e000e000e000e000e000e000e000e001, type: 2}
    """), encoding="utf-8")
    _make_meta(scene.with_suffix(".unity.meta"), "f000f000f000f000f000f000f000f001")

    # --- Prefab ---
    prefab = assets / "Lamp.prefab"
    prefab.write_text(textwrap.dedent("""\
        %YAML 1.1
        %TAG !u! tag:unity3d.com,2011:
        --- !u!1 &1000
        GameObject:
          m_Name: LampRoot
          m_IsActive: 1
          m_Layer: 0
          m_TagString: Untagged
        --- !u!4 &2000
        Transform:
          m_GameObject: {fileID: 1000}
          m_LocalPosition: {x: 0, y: 3, z: 0}
          m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
          m_LocalScale: {x: 1, y: 1, z: 1}
          m_Father: {fileID: 0}
          m_Children: []
    """), encoding="utf-8")
    _make_meta(prefab.with_suffix(".prefab.meta"), "b000b000b000b000b000b000b000b001")

    # --- ScriptableObject .asset ---
    so = assets / "GameConfig.asset"
    so.write_text(textwrap.dedent("""\
        %YAML 1.1
        %TAG !u! tag:unity3d.com,2011:
        --- !u!114 &11400000
        MonoBehaviour:
          m_ObjectHideFlags: 0
          m_Script: {fileID: 0}
          m_Name: GameConfig
          maxPlayers: 8
          roundDuration: 120
          mapName: TestArena
    """), encoding="utf-8")
    _make_meta(so.with_suffix(".asset.meta"), "b000b000b000b000b000b000b000b002")

    return root


class TestEndToEnd:
    """Full pipeline integration tests."""

    def test_full_conversion_produces_rbxl(self, full_unity_project: Path, tmp_path: Path) -> None:
        """Run the full pipeline and verify the .rbxl file is written."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])

        # Pipeline should complete without crashing
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        # .rbxl file must exist
        rbxl = output_dir / "converted_place.rbxl"
        assert rbxl.exists(), f"No .rbxl file found. Output:\n{result.output}"
        assert rbxl.stat().st_size > 0

    def test_report_json_is_valid(self, full_unity_project: Path, tmp_path: Path) -> None:
        """Conversion report should be valid JSON with expected fields."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        report_path = output_dir / "conversion_report.json"
        assert report_path.exists()

        report = json.loads(report_path.read_text())
        assert "success" in report
        assert "assets" in report
        assert "materials" in report
        assert "scripts" in report
        assert "scene" in report
        assert "output" in report
        assert report["scene"]["scenes_parsed"] >= 1

    def test_scripts_transpiled(self, full_unity_project: Path, tmp_path: Path) -> None:
        """C# scripts should be transpiled (rule-based when --no-ai)."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])
        assert result.exit_code == 0

        report = json.loads((output_dir / "conversion_report.json").read_text())
        assert report["scripts"]["total"] >= 1

    def test_materials_mapped(self, full_unity_project: Path, tmp_path: Path) -> None:
        """Materials should be processed and mapped."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])
        assert result.exit_code == 0

        report = json.loads((output_dir / "conversion_report.json").read_text())
        assert report["materials"]["total"] >= 1

    def test_rbxl_contains_parts(self, full_unity_project: Path, tmp_path: Path) -> None:
        """The .rbxl XML should contain Workspace items."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])
        assert result.exit_code == 0

        rbxl_content = (output_dir / "converted_place.rbxl").read_text()
        assert "Workspace" in rbxl_content
        assert "FloorObject" in rbxl_content

    def test_scriptable_objects_converted(self, full_unity_project: Path, tmp_path: Path) -> None:
        """ScriptableObject .asset files should be converted to ModuleScripts."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])
        assert result.exit_code == 0
        # Check the output mentions ScriptableObject conversion
        assert "ScriptableObject" in result.output or "asset" in result.output.lower()

    def test_unconverted_md_generated(self, full_unity_project: Path, tmp_path: Path) -> None:
        """UNCONVERTED.md should be generated."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])
        assert result.exit_code == 0

        unconverted = output_dir / "UNCONVERTED.md"
        assert unconverted.exists()

    def test_no_errors_in_report(self, full_unity_project: Path, tmp_path: Path) -> None:
        """A clean project should produce no errors."""
        output_dir = tmp_path / "output"
        runner = CliRunner()
        result = runner.invoke(convert, [
            str(full_unity_project),
            str(output_dir),
            "--no-ai",
            "--no-decimate",
        ])
        assert result.exit_code == 0

        report = json.loads((output_dir / "conversion_report.json").read_text())
        assert report["success"] is True
        assert report["errors"] == []
