"""
Shared fixtures for black-box regression tests.

Provides reusable temporary Unity project structures that modules
can be pointed at, without relying on any real Unity project being present.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ── Minimal Unity .meta file ────────────────────────────────────────────

def make_meta(path: Path, guid: str, is_folder: bool = False) -> None:
    """Write a minimal Unity .meta file."""
    folder_line = "folderAsset: yes\n" if is_folder else ""
    path.write_text(
        f"fileFormatVersion: 2\n"
        f"guid: {guid}\n"
        f"{folder_line}"
        f"NativeFormatImporter:\n"
        f"  userData:\n",
        encoding="utf-8",
    )


# ── Minimal Unity .mat file ────────────────────────────────────────────

STANDARD_MAT_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!21 &2100000
    Material:
      m_Name: TestStandard
      m_Shader: {fileID: 46}
      m_ShaderKeywords: _EMISSION
      m_InvalidKeywords: []
      m_SavedProperties:
        m_TexEnvs:
          - _MainTex:
              m_Texture: {fileID: 2800000, guid: aaaa0000aaaa0000aaaa0000aaaa0001, type: 3}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
          - _BumpMap:
              m_Texture: {fileID: 2800000, guid: aaaa0000aaaa0000aaaa0000aaaa0002, type: 3}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
          - _MetallicGlossMap:
              m_Texture: {fileID: 0}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
          - _OcclusionMap:
              m_Texture: {fileID: 0}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
          - _EmissionMap:
              m_Texture: {fileID: 0}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
        m_Floats:
          - _Metallic: 0.2
          - _Glossiness: 0.6
          - _BumpScale: 1
          - _OcclusionStrength: 1
          - _Mode: 0
          - _Cutoff: 0.5
          - _GlossMapScale: 1
        m_Colors:
          - _Color: {r: 0.8, g: 0.2, b: 0.1, a: 1}
          - _EmissionColor: {r: 0, g: 0, b: 0, a: 1}
""")


URP_UNLIT_MAT_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!21 &2100000
    Material:
      m_Name: TestURPUnlit
      m_Shader: {fileID: 0, guid: bbbb0000bbbb0000bbbb0000bbbb0000, type: 3}
      m_SavedProperties:
        m_TexEnvs:
          - _BaseMap:
              m_Texture: {fileID: 2800000, guid: aaaa0000aaaa0000aaaa0000aaaa0001, type: 3}
              m_Scale: {x: 2, y: 2}
              m_Offset: {x: 0, y: 0}
        m_Floats: []
        m_Colors:
          - _BaseColor: {r: 1, g: 1, b: 1, a: 1}
""")


URP_LIT_MAT_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!21 &2100000
    Material:
      m_Name: TestURPLit
      m_Shader: {fileID: 0, guid: cccc0000cccc0000cccc0000cccc0000, type: 3}
      m_SavedProperties:
        m_TexEnvs:
          - _BaseMap:
              m_Texture: {fileID: 2800000, guid: aaaa0000aaaa0000aaaa0000aaaa0001, type: 3}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
          - _BumpMap:
              m_Texture: {fileID: 2800000, guid: aaaa0000aaaa0000aaaa0000aaaa0002, type: 3}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
          - _MetallicGlossMap:
              m_Texture: {fileID: 2800000, guid: aaaa0000aaaa0000aaaa0000aaaa0003, type: 3}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
        m_Floats:
          - _Metallic: 0.5
          - _Smoothness: 0.7
        m_Colors:
          - _BaseColor: {r: 0.5, g: 0.5, b: 0.5, a: 1}
""")


PARTICLE_MAT_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!21 &2100000
    Material:
      m_Name: TestParticle
      m_Shader: {fileID: 200}
      m_SavedProperties:
        m_TexEnvs:
          - _MainTex:
              m_Texture: {fileID: 2800000, guid: aaaa0000aaaa0000aaaa0000aaaa0001, type: 3}
              m_Scale: {x: 1, y: 1}
              m_Offset: {x: 0, y: 0}
        m_Floats: []
        m_Colors:
          - _TintColor: {r: 1, g: 0.5, b: 0, a: 1}
""")


# ── Minimal Unity .unity scene ──────────────────────────────────────────

MINIMAL_SCENE_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!1 &100
    GameObject:
      m_Name: MainCamera
      m_IsActive: 1
      m_Layer: 0
      m_TagString: MainCamera
    --- !u!4 &200
    Transform:
      m_GameObject: {fileID: 100}
      m_LocalPosition: {x: 0, y: 5, z: -10}
      m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
      m_LocalScale: {x: 1, y: 1, z: 1}
      m_Father: {fileID: 0}
      m_Children: [{fileID: 400}]
    --- !u!1 &300
    GameObject:
      m_Name: Cube
      m_IsActive: 1
      m_Layer: 0
      m_TagString: Untagged
    --- !u!4 &400
    Transform:
      m_GameObject: {fileID: 300}
      m_LocalPosition: {x: 1, y: 2, z: 3}
      m_LocalRotation: {x: 0, y: 0.707, z: 0, w: 0.707}
      m_LocalScale: {x: 2, y: 2, z: 2}
      m_Father: {fileID: 200}
      m_Children: []
    --- !u!33 &500
    MeshFilter:
      m_GameObject: {fileID: 300}
      m_Mesh: {fileID: 4300000, guid: dddd0000dddd0000dddd0000dddd0001, type: 3}
    --- !u!23 &600
    MeshRenderer:
      m_GameObject: {fileID: 300}
      m_Materials:
        - {fileID: 2100000, guid: eeee0000eeee0000eeee0000eeee0001, type: 2}
""")


SCENE_WITH_PREFAB_INSTANCE_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!1 &100
    GameObject:
      m_Name: WorldRoot
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
    --- !u!1001 &900
    PrefabInstance:
      m_SourcePrefab: {fileID: 100100000, guid: ffff0000ffff0000ffff0000ffff0001, type: 3}
      m_Modification:
        m_TransformParent: {fileID: 200}
        m_Modifications:
          - target: {fileID: 1000}
            propertyPath: m_LocalPosition.x
            value: 42.5
          - target: {fileID: 1000}
            propertyPath: m_LocalPosition.y
            value: 10.0
          - target: {fileID: 1000}
            propertyPath: m_Name
            value: OverriddenName
        m_RemovedComponents: []
""")


# ── Minimal Unity .prefab ───────────────────────────────────────────────

MINIMAL_PREFAB_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!1 &1000
    GameObject:
      m_Name: PrefabRoot
      m_IsActive: 1
      m_Layer: 0
      m_TagString: Untagged
    --- !u!4 &2000
    Transform:
      m_GameObject: {fileID: 1000}
      m_LocalPosition: {x: 0, y: 0, z: 0}
      m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
      m_LocalScale: {x: 1, y: 1, z: 1}
      m_Father: {fileID: 0}
      m_Children: [{fileID: 4000}]
    --- !u!1 &3000
    GameObject:
      m_Name: ChildMesh
      m_IsActive: 1
      m_Layer: 0
      m_TagString: Untagged
    --- !u!4 &4000
    Transform:
      m_GameObject: {fileID: 3000}
      m_LocalPosition: {x: 5, y: 0, z: 0}
      m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
      m_LocalScale: {x: 1, y: 1, z: 1}
      m_Father: {fileID: 2000}
      m_Children: []
    --- !u!33 &5000
    MeshFilter:
      m_GameObject: {fileID: 3000}
      m_Mesh: {fileID: 4300000, guid: aaaa1111aaaa1111aaaa1111aaaa1111, type: 3}
    --- !u!23 &6000
    MeshRenderer:
      m_GameObject: {fileID: 3000}
      m_Materials:
        - {fileID: 2100000, guid: bbbb1111bbbb1111bbbb1111bbbb1111, type: 2}
""")


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def unity_project(tmp_path: Path) -> Path:
    """
    Create a minimal Unity project structure in a temp directory.
    Contains Assets/ with a texture, a material, a .cs script, and proper .meta files.
    """
    root = tmp_path / "TestProject"
    assets = root / "Assets"
    assets.mkdir(parents=True)

    # Create a small PNG texture (1x1 pixel, red)
    tex = assets / "red.png"
    # Minimal valid PNG: 1x1 red pixel
    import struct, zlib
    def _make_1px_png(r: int, g: int, b: int) -> bytes:
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
    tex.write_bytes(_make_1px_png(255, 0, 0))
    make_meta(tex.with_suffix(".png.meta"), "aaaa0000aaaa0000aaaa0000aaaa0001")

    # Another texture for normal map
    tex2 = assets / "normal.png"
    tex2.write_bytes(_make_1px_png(128, 128, 255))
    make_meta(tex2.with_suffix(".png.meta"), "aaaa0000aaaa0000aaaa0000aaaa0002")

    # Metallic texture
    tex3 = assets / "metallic.png"
    tex3.write_bytes(_make_1px_png(0, 0, 0))
    make_meta(tex3.with_suffix(".png.meta"), "aaaa0000aaaa0000aaaa0000aaaa0003")

    # .mat file (Standard shader)
    mat = assets / "TestStandard.mat"
    mat.write_text(STANDARD_MAT_YAML, encoding="utf-8")
    make_meta(mat.with_suffix(".mat.meta"), "eeee0000eeee0000eeee0000eeee0001")

    # URP Unlit .mat
    mat_urp = assets / "TestURPUnlit.mat"
    mat_urp.write_text(URP_UNLIT_MAT_YAML, encoding="utf-8")
    make_meta(mat_urp.with_suffix(".mat.meta"), "eeee0000eeee0000eeee0000eeee0002")

    # URP Lit .mat
    mat_urp_lit = assets / "TestURPLit.mat"
    mat_urp_lit.write_text(URP_LIT_MAT_YAML, encoding="utf-8")
    make_meta(mat_urp_lit.with_suffix(".mat.meta"), "eeee0000eeee0000eeee0000eeee0003")

    # Particle .mat
    mat_particle = assets / "TestParticle.mat"
    mat_particle.write_text(PARTICLE_MAT_YAML, encoding="utf-8")
    make_meta(mat_particle.with_suffix(".mat.meta"), "eeee0000eeee0000eeee0000eeee0004")

    # .cs script
    script = assets / "PlayerController.cs"
    script.write_text(
        "using UnityEngine;\n"
        "public class PlayerController : MonoBehaviour {\n"
        "    float speed = 5.0f;\n"
        "    void Update() {\n"
        "        Debug.Log(\"tick\");\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    make_meta(script.with_suffix(".cs.meta"), "cccc0000cccc0000cccc0000cccc0001")

    # .unity scene
    scene = assets / "Main.unity"
    scene.write_text(MINIMAL_SCENE_YAML, encoding="utf-8")
    make_meta(scene.with_suffix(".unity.meta"), "dddd0000dddd0000dddd0000dddd0002")

    # .prefab
    prefab = assets / "TestPrefab.prefab"
    prefab.write_text(MINIMAL_PREFAB_YAML, encoding="utf-8")
    make_meta(prefab.with_suffix(".prefab.meta"), "ffff0000ffff0000ffff0000ffff0001")

    # .obj mesh
    mesh = assets / "cube.obj"
    mesh.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
        "v 0 0 1\nv 1 0 1\nv 1 1 1\nv 0 1 1\n"
        "f 1 2 3 4\nf 5 6 7 8\nf 1 2 6 5\n"
        "f 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n",
        encoding="utf-8",
    )
    make_meta(mesh.with_suffix(".obj.meta"), "dddd0000dddd0000dddd0000dddd0001")

    return root


@pytest.fixture
def unity_project_with_prefab_instance(unity_project: Path) -> Path:
    """Extend unity_project with a scene that references a PrefabInstance."""
    scene = unity_project / "Assets" / "PrefabScene.unity"
    scene.write_text(SCENE_WITH_PREFAB_INSTANCE_YAML, encoding="utf-8")
    make_meta(scene.with_suffix(".unity.meta"), "dddd0000dddd0000dddd0000dddd0099")
    return unity_project
