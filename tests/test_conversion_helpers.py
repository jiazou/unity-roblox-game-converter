"""Tests for the component conversion helpers in modules/conversion_helpers.py.

Covers the 6 broken-out helper functions:
  - roblox_def_to_surface_appearance
  - apply_collider_properties
  - convert_light_components
  - convert_audio_components
  - convert_particle_components
  - apply_materials
  - extract_serialized_field_refs
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules import guid_resolver, material_mapper, prefab_parser, rbxl_writer, scene_parser
from modules.conversion_helpers import (
    roblox_def_to_surface_appearance,
    apply_collider_properties,
    convert_light_components,
    convert_audio_components,
    convert_particle_components,
    apply_materials,
    extract_serialized_field_refs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _part(name: str = "TestPart") -> rbxl_writer.RbxPartEntry:
    return rbxl_writer.RbxPartEntry(name=name)


def _comp(ctype: str, **props) -> scene_parser.ComponentData:
    return scene_parser.ComponentData(
        component_type=ctype, file_id="1", properties=props,
    )


def _snode(name: str = "Node", file_id: str = "100", **kwargs) -> scene_parser.SceneNode:
    defaults = dict(active=True, layer=0, tag="Untagged")
    defaults.update(kwargs)
    return scene_parser.SceneNode(name=name, file_id=file_id, **defaults)


# ---------------------------------------------------------------------------
# roblox_def_to_surface_appearance
# ---------------------------------------------------------------------------

class TestRobloxDefToSurfaceAppearance:
    def test_maps_all_fields(self) -> None:
        rdef = material_mapper.RobloxMaterialDef(
            color_map="tex/albedo.png",
            normal_map="tex/normal.png",
            metalness_map="tex/metal.png",
            roughness_map="tex/rough.png",
            emissive_mask="tex/emissive.png",
            emissive_strength=2.5,
            emissive_tint=(1.0, 0.5, 0.0),
            color_tint=(0.8, 0.8, 0.8),
            alpha_mode="Transparency",
        )
        sa = roblox_def_to_surface_appearance(rdef)
        assert sa.color_map == "tex/albedo.png"
        assert sa.normal_map == "tex/normal.png"
        assert sa.metalness_map == "tex/metal.png"
        assert sa.roughness_map == "tex/rough.png"
        assert sa.emissive_mask == "tex/emissive.png"
        assert sa.emissive_strength == 2.5
        assert sa.emissive_tint == (1.0, 0.5, 0.0)
        assert sa.color_tint == (0.8, 0.8, 0.8)
        assert sa.alpha_mode == "Transparency"

    def test_defaults(self) -> None:
        rdef = material_mapper.RobloxMaterialDef()
        sa = roblox_def_to_surface_appearance(rdef)
        assert sa.color_map is None
        assert sa.alpha_mode == "Opaque"
        assert sa.emissive_strength == 1.0

    def test_returns_correct_type(self) -> None:
        sa = roblox_def_to_surface_appearance(material_mapper.RobloxMaterialDef())
        assert isinstance(sa, rbxl_writer.RbxSurfaceAppearance)


# ---------------------------------------------------------------------------
# apply_collider_properties
# ---------------------------------------------------------------------------

class TestApplyColliderProperties:
    def test_box_collider(self) -> None:
        part = _part()
        comps = [_comp("BoxCollider", m_Size={"x": 2.0, "y": 3.0, "z": 4.0})]
        apply_collider_properties(part, comps)
        assert part.anchored is False
        assert part.size == (2.0, 3.0, 4.0)

    def test_sphere_collider(self) -> None:
        part = _part()
        comps = [_comp("SphereCollider", m_Radius=1.5)]
        apply_collider_properties(part, comps)
        assert part.anchored is False
        assert part.size == (3.0, 3.0, 3.0)

    def test_capsule_collider(self) -> None:
        part = _part()
        comps = [_comp("CapsuleCollider", m_Radius=0.5, m_Height=2.0)]
        apply_collider_properties(part, comps)
        assert part.anchored is False
        assert part.size == (1.0, 2.0, 1.0)

    def test_rigidbody_kinematic(self) -> None:
        part = _part()
        part.anchored = False
        comps = [_comp("Rigidbody", m_IsKinematic=1)]
        apply_collider_properties(part, comps)
        assert part.anchored is True

    def test_rigidbody_dynamic(self) -> None:
        part = _part()
        comps = [_comp("Rigidbody", m_IsKinematic=0)]
        apply_collider_properties(part, comps)
        assert part.anchored is False

    def test_no_colliders(self) -> None:
        part = _part()
        comps = [_comp("MeshRenderer")]
        apply_collider_properties(part, comps)
        assert part.anchored is True  # unchanged default

    def test_box_collider_default_size(self) -> None:
        part = _part()
        comps = [_comp("BoxCollider")]
        apply_collider_properties(part, comps)
        assert part.anchored is False
        # No m_Size → size stays at default part size

    def test_multiple_colliders_last_wins(self) -> None:
        part = _part()
        comps = [
            _comp("BoxCollider", m_Size={"x": 1, "y": 1, "z": 1}),
            _comp("SphereCollider", m_Radius=2.0),
        ]
        apply_collider_properties(part, comps)
        assert part.size == (4.0, 4.0, 4.0)  # sphere last


# ---------------------------------------------------------------------------
# convert_light_components
# ---------------------------------------------------------------------------

class TestConvertLightComponents:
    def test_point_light(self) -> None:
        part = _part()
        comps = [_comp("Light",
            m_Type=2,
            m_Color={"r": 1.0, "g": 0.5, "b": 0.0},
            m_Intensity=2.0,
            m_Range=15.0,
            m_Shadows=0,
        )]
        convert_light_components(part, comps)
        assert len(part.light_children) == 1
        lc = part.light_children[0]
        assert lc[0] == "PointLight"
        assert lc[1] == (1.0, 0.5, 0.0)  # color
        assert lc[2] == 2.0  # intensity
        assert lc[3] == 15.0  # range

    def test_spot_light(self) -> None:
        part = _part()
        comps = [_comp("Light",
            m_Type=0,
            m_Color={"r": 1.0, "g": 1.0, "b": 1.0},
            m_Intensity=1.0,
            m_Range=10.0,
            m_Shadows=1,
            m_SpotAngle=45.0,
        )]
        convert_light_components(part, comps)
        assert len(part.light_children) == 1
        lc = part.light_children[0]
        assert lc[0] == "SpotLight"
        assert lc[4] is True  # shadows
        assert lc[5] == 45.0  # spot angle

    def test_directional_light_ignored(self) -> None:
        """Directional lights (type=1) have no per-part Roblox equivalent."""
        part = _part()
        comps = [_comp("Light", m_Type=1)]
        convert_light_components(part, comps)
        assert len(part.light_children) == 0

    def test_non_light_components_ignored(self) -> None:
        part = _part()
        comps = [_comp("MeshRenderer"), _comp("AudioSource")]
        convert_light_components(part, comps)
        assert len(part.light_children) == 0

    def test_default_light_values(self) -> None:
        part = _part()
        comps = [_comp("Light")]  # all defaults
        convert_light_components(part, comps)
        assert len(part.light_children) == 1
        lc = part.light_children[0]
        assert lc[0] == "PointLight"  # default type 2
        assert lc[2] == 1.0  # default intensity

    def test_shadows_as_dict(self) -> None:
        part = _part()
        comps = [_comp("Light", m_Type=2, m_Shadows={"m_Type": 2})]
        convert_light_components(part, comps)
        assert part.light_children[0][4] is True


# ---------------------------------------------------------------------------
# convert_audio_components
# ---------------------------------------------------------------------------

class TestConvertAudioComponents:
    def test_audio_source(self) -> None:
        part = _part()
        comps = [_comp("AudioSource",
            m_audioClip={"guid": "audio123", "fileID": 100},
            m_Volume=0.8,
            m_Pitch=1.2,
            m_Loop=1,
            m_PlayOnAwake=0,
            m_MinDistance=2.0,
            m_MaxDistance=100.0,
        )]
        convert_audio_components(part, "MyNode", comps, None)
        assert len(part.sound_children) == 1
        sc = part.sound_children[0]
        assert sc[0] == "MyNode_Sound"
        assert sc[2] == pytest.approx(0.8)  # volume
        assert sc[3] is True  # loop
        assert sc[4] == pytest.approx(1.2)  # pitch

    def test_no_audio_sources(self) -> None:
        part = _part()
        comps = [_comp("Light")]
        convert_audio_components(part, "Node", comps, None)
        assert len(part.sound_children) == 0

    def test_default_audio_values(self) -> None:
        part = _part()
        comps = [_comp("AudioSource")]
        convert_audio_components(part, "Node", comps, None)
        assert len(part.sound_children) == 1
        sc = part.sound_children[0]
        assert sc[2] == 1.0  # default volume
        assert sc[4] == 1.0  # default pitch
        assert sc[6] == 1.0  # default min distance
        assert sc[7] == 500.0  # default max distance

    def test_multiple_audio_sources(self) -> None:
        part = _part()
        comps = [
            _comp("AudioSource", m_Volume=0.5),
            _comp("AudioSource", m_Volume=0.9),
        ]
        convert_audio_components(part, "Node", comps, None)
        assert len(part.sound_children) == 2


# ---------------------------------------------------------------------------
# convert_particle_components
# ---------------------------------------------------------------------------

class TestConvertParticleComponents:
    def test_particle_system(self) -> None:
        part = _part()
        comps = [_comp("ParticleSystem",
            InitialModule={
                "startLifetime": {"scalar": 3.0},
                "startSpeed": {"scalar": 2.0},
                "startSize": {"scalar": 0.5},
                "startColor": {"maxColor": {"r": 255, "g": 128, "b": 0}},
            },
            EmissionModule={
                "rateOverTime": {"scalar": 20.0},
            },
        )]
        convert_particle_components(part, "Fire", comps)
        assert len(part.particle_children) == 1
        pc = part.particle_children[0]
        assert pc[0] == "Fire_Particles"
        assert pc[1] == pytest.approx(20.0)  # rate
        assert pc[2] == pytest.approx(3.0)   # lifetime
        assert pc[4] == pytest.approx(2.0)   # speed
        assert pc[6] == pytest.approx(0.5)   # size

    def test_default_particle_values(self) -> None:
        part = _part()
        comps = [_comp("ParticleSystem")]
        convert_particle_components(part, "Emitter", comps)
        assert len(part.particle_children) == 1
        pc = part.particle_children[0]
        assert pc[0] == "Emitter_Particles"
        assert pc[2] == pytest.approx(5.0)  # default lifetime
        assert pc[4] == pytest.approx(5.0)  # default speed
        assert pc[6] == pytest.approx(1.0)  # default size

    def test_no_particle_systems(self) -> None:
        part = _part()
        comps = [_comp("MeshRenderer")]
        convert_particle_components(part, "Node", comps)
        assert len(part.particle_children) == 0

    def test_color_normalization(self) -> None:
        """Colors > 1 should be normalized from 0-255 to 0-1 range."""
        part = _part()
        comps = [_comp("ParticleSystem",
            InitialModule={
                "startColor": {"maxColor": {"r": 255, "g": 0, "b": 128}},
            },
        )]
        convert_particle_components(part, "P", comps)
        pc = part.particle_children[0]
        color = pc[7]
        assert color[0] == pytest.approx(1.0)
        assert color[1] == pytest.approx(0.0)
        assert color[2] == pytest.approx(128.0 / 255.0, abs=0.01)

    def test_scalar_as_direct_float(self) -> None:
        """startLifetime can be a plain float instead of a dict."""
        part = _part()
        comps = [_comp("ParticleSystem",
            InitialModule={
                "startLifetime": 7.0,
                "startSpeed": 3.0,
                "startSize": 2.0,
            },
            EmissionModule={
                "rateOverTime": 5.0,
            },
        )]
        convert_particle_components(part, "P", comps)
        pc = part.particle_children[0]
        assert pc[2] == pytest.approx(7.0)
        assert pc[4] == pytest.approx(3.0)
        assert pc[6] == pytest.approx(2.0)
        assert pc[1] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# apply_materials
# ---------------------------------------------------------------------------

class TestApplyMaterials:
    def test_applies_material_from_mesh_renderer(self) -> None:
        part = _part()
        node = _snode(components=[
            scene_parser.ComponentData(
                component_type="MeshRenderer",
                file_id="500",
                properties={"m_Materials": [{"guid": "mat_guid_1"}]},
            ),
        ])
        rdef = material_mapper.RobloxMaterialDef(
            color_map="tex/albedo.png",
            base_part_color=(0.5, 0.3, 0.1),
            base_part_transparency=0.2,
        )
        guid_to_def = {"mat_guid_1": rdef}
        apply_materials(part, node, guid_to_def, None)
        assert part.surface_appearance is not None
        assert part.surface_appearance.color_map == "tex/albedo.png"
        assert part.color3 == (0.5, 0.3, 0.1)
        assert part.transparency == pytest.approx(0.2)

    def test_no_material_defs(self) -> None:
        part = _part()
        node = _snode(components=[
            scene_parser.ComponentData(
                component_type="MeshRenderer",
                file_id="500",
                properties={"m_Materials": [{"guid": "unknown"}]},
            ),
        ])
        apply_materials(part, node, None, None)
        assert part.surface_appearance is None

    def test_empty_guid_map(self) -> None:
        part = _part()
        node = _snode(components=[
            scene_parser.ComponentData(
                component_type="MeshRenderer",
                file_id="500",
                properties={"m_Materials": [{"guid": "missing"}]},
            ),
        ])
        apply_materials(part, node, {}, None)
        assert part.surface_appearance is None

    def test_companion_scripts_attached(self) -> None:
        part = _part()
        node = _snode(name="Lamp", components=[
            scene_parser.ComponentData(
                component_type="MeshRenderer",
                file_id="500",
                properties={"m_Materials": [{"guid": "mat1"}]},
            ),
        ])
        rdef = material_mapper.RobloxMaterialDef()
        guid_to_def = {"mat1": rdef}
        scripts = {"mat1": ["-- blink script", "-- rotation script"]}
        apply_materials(part, node, guid_to_def, scripts)
        assert len(part.scripts) == 2
        assert part.scripts[0].name == "Lamp_MaterialEffect"
        assert part.scripts[1].name == "Lamp_MaterialEffect_2"
        assert part.scripts[0].luau_source == "-- blink script"

    def test_skinned_mesh_renderer(self) -> None:
        part = _part()
        node = _snode(components=[
            scene_parser.ComponentData(
                component_type="SkinnedMeshRenderer",
                file_id="500",
                properties={"m_Materials": [{"guid": "skin_mat"}]},
            ),
        ])
        rdef = material_mapper.RobloxMaterialDef(color_map="tex/skin.png")
        apply_materials(part, node, {"skin_mat": rdef}, None)
        assert part.surface_appearance is not None
        assert part.surface_appearance.color_map == "tex/skin.png"

    def test_first_material_used(self) -> None:
        """Only the first matching material is applied to the part."""
        part = _part()
        node = _snode(components=[
            scene_parser.ComponentData(
                component_type="MeshRenderer",
                file_id="500",
                properties={"m_Materials": [
                    {"guid": "mat_a"},
                    {"guid": "mat_b"},
                ]},
            ),
        ])
        rdef_a = material_mapper.RobloxMaterialDef(color_map="tex/a.png")
        rdef_b = material_mapper.RobloxMaterialDef(color_map="tex/b.png")
        apply_materials(part, node, {"mat_a": rdef_a, "mat_b": rdef_b}, None)
        assert part.surface_appearance.color_map == "tex/a.png"

    def test_non_renderer_components_ignored(self) -> None:
        part = _part()
        node = _snode(components=[
            scene_parser.ComponentData(
                component_type="Light",
                file_id="500",
                properties={"m_Materials": [{"guid": "mat1"}]},
            ),
        ])
        rdef = material_mapper.RobloxMaterialDef(color_map="tex/a.png")
        apply_materials(part, node, {"mat1": rdef}, None)
        assert part.surface_appearance is None


# ---------------------------------------------------------------------------
# extract_serialized_field_refs
# ---------------------------------------------------------------------------

def _make_guid_index(tmp_path, entries):
    """Build a GuidIndex with the given (guid, rel_path, suffix) entries.

    Creates real files so that ``resolve()`` returns valid absolute paths.
    """
    gi = guid_resolver.GuidIndex(project_root=tmp_path)
    for guid, rel_path_str, suffix in entries:
        asset_path = tmp_path / rel_path_str
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("", encoding="utf-8")
        gi.guid_to_entry[guid] = guid_resolver.GuidEntry(
            guid=guid,
            asset_path=asset_path.resolve(),
            relative_path=Path(rel_path_str),
            kind="prefab" if suffix == ".prefab" else "script",
            is_directory=False,
        )
        gi.path_to_guid[asset_path.resolve()] = guid
    return gi


class TestExtractSerializedFieldRefs:
    def test_extracts_prefab_ref_from_scene(self, tmp_path):
        """A MonoBehaviour with [SerializeField] GameObject field gets extracted."""
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Spawner.cs", ".cs"),
            ("prefab_guid_1", "Assets/Prefabs/Enemy.prefab", ".prefab"),
        ])
        node = _snode(
            name="SpawnPoint",
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_ObjectHideFlags": 0,
                        "m_GameObject": {"fileID": 100},
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_Name": "",
                        "enemyPrefab": {"fileID": 0, "guid": "prefab_guid_1", "type": 3},
                        "spawnRate": 5.0,
                    },
                ),
            ],
        )
        scene = scene_parser.ParsedScene(
            scene_path=tmp_path / "test.unity",
            all_nodes={"100": node},
            roots=[node],
        )
        prefab_lib = prefab_parser.PrefabLibrary()
        result = extract_serialized_field_refs([scene], prefab_lib, gi)

        script_path = (tmp_path / "Assets/Scripts/Spawner.cs").resolve()
        assert script_path in result
        assert result[script_path] == {"enemyPrefab": "Enemy"}

    def test_ignores_non_prefab_refs(self, tmp_path):
        """Object references to non-prefab assets (e.g. materials) are skipped."""
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Player.cs", ".cs"),
            ("mat_guid_1", "Assets/Materials/Red.mat", ".mat"),
        ])
        node = _snode(
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_GameObject": {"fileID": 100},
                        "myMaterial": {"fileID": 0, "guid": "mat_guid_1", "type": 3},
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
        assert len(result) == 0

    def test_ignores_internal_m_properties(self, tmp_path):
        """Properties starting with m_ should be skipped (Unity internals)."""
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Test.cs", ".cs"),
            ("prefab_guid_1", "Assets/Prefabs/Thing.prefab", ".prefab"),
        ])
        node = _snode(
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_GameObject": {"fileID": 100},
                        "m_PrefabInstance": {"fileID": 0, "guid": "prefab_guid_1", "type": 3},
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
        assert len(result) == 0

    def test_extracts_from_prefab_library(self, tmp_path):
        """Serialized refs from prefab template MonoBehaviours are also extracted."""
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Turret.cs", ".cs"),
            ("prefab_guid_1", "Assets/Prefabs/Bullet.prefab", ".prefab"),
        ])
        pcomp = prefab_parser.PrefabComponent(
            component_type="MonoBehaviour",
            file_id="300",
            properties={
                "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                "m_GameObject": {"fileID": 100},
                "bulletPrefab": {"fileID": 0, "guid": "prefab_guid_1", "type": 3},
            },
        )
        pnode = prefab_parser.PrefabNode(
            name="Turret",
            file_id="100",
            active=True,
            components=[pcomp],
        )
        template = prefab_parser.PrefabTemplate(
            name="Turret",
            prefab_path=tmp_path / "Assets/Prefabs/Turret.prefab",
            root=pnode,
        )
        lib = prefab_parser.PrefabLibrary(prefabs=[template])

        result = extract_serialized_field_refs([], lib, gi)
        script_path = (tmp_path / "Assets/Scripts/Turret.cs").resolve()
        assert script_path in result
        assert result[script_path] == {"bulletPrefab": "Bullet"}

    def test_multiple_fields_same_script(self, tmp_path):
        """Multiple serialized fields on the same script are all captured."""
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Spawner.cs", ".cs"),
            ("prefab_guid_1", "Assets/Prefabs/Enemy.prefab", ".prefab"),
            ("prefab_guid_2", "Assets/Prefabs/Coin.prefab", ".prefab"),
        ])
        node = _snode(
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_GameObject": {"fileID": 100},
                        "enemyPrefab": {"fileID": 0, "guid": "prefab_guid_1", "type": 3},
                        "coinPrefab": {"fileID": 0, "guid": "prefab_guid_2", "type": 3},
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
        script_path = (tmp_path / "Assets/Scripts/Spawner.cs").resolve()
        assert result[script_path] == {"enemyPrefab": "Enemy", "coinPrefab": "Coin"}

    def test_zero_guid_ignored(self, tmp_path):
        """References with all-zero GUIDs are skipped."""
        gi = _make_guid_index(tmp_path, [
            ("script_guid_1", "Assets/Scripts/Test.cs", ".cs"),
        ])
        node = _snode(
            components=[
                scene_parser.ComponentData(
                    component_type="MonoBehaviour",
                    file_id="200",
                    properties={
                        "m_Script": {"fileID": 11500000, "guid": "script_guid_1", "type": 3},
                        "m_GameObject": {"fileID": 100},
                        "emptyRef": {"fileID": 0, "guid": "00000000000000000000000000000000", "type": 3},
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
        assert len(result) == 0
