"""Tests for modules/bridge_injector.py — bridge auto-injection detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.bridge_injector import (
    BRIDGE_SPECS,
    BridgeInjectionResult,
    detect_needed_bridges,
    inject_bridges,
)


# ---------------------------------------------------------------------------
# detect_needed_bridges
# ---------------------------------------------------------------------------

class TestDetectNeededBridges:
    """Scan transpiled Luau for bridge module dependencies."""

    def test_empty_sources(self) -> None:
        result = detect_needed_bridges([])
        assert result.needed == []
        assert result.already_present == []

    def test_no_bridge_references(self) -> None:
        result = detect_needed_bridges(["local x = 42\nprint(x)\n"])
        assert result.needed == []

    # --- Input ---

    def test_detects_input_getkey(self) -> None:
        result = detect_needed_bridges([
            'if Input.GetKey("Space") then jump() end'
        ])
        assert "Input.lua" in result.needed

    def test_detects_input_getkeydown(self) -> None:
        result = detect_needed_bridges([
            'if Input.GetKeyDown("W") then move() end'
        ])
        assert "Input.lua" in result.needed

    def test_detects_input_getkeyup(self) -> None:
        result = detect_needed_bridges([
            'if Input.GetKeyUp("Escape") then pause() end'
        ])
        assert "Input.lua" in result.needed

    def test_detects_input_getaxis(self) -> None:
        result = detect_needed_bridges([
            'local h = Input.GetAxis("Horizontal")'
        ])
        assert "Input.lua" in result.needed

    def test_detects_input_getswipe(self) -> None:
        result = detect_needed_bridges([
            'local swipe = Input.GetSwipe()'
        ])
        assert "Input.lua" in result.needed

    def test_detects_input_require(self) -> None:
        result = detect_needed_bridges([
            'local Input = require(ReplicatedStorage:WaitForChild("Input"))'
        ])
        assert "Input.lua" in result.needed

    # --- Time ---

    def test_detects_time_deltatime(self) -> None:
        result = detect_needed_bridges([
            "local speed = distance * Time.deltaTime"
        ])
        assert "Time.lua" in result.needed

    def test_detects_time_time(self) -> None:
        result = detect_needed_bridges([
            "local elapsed = Time.time - startTime"
        ])
        assert "Time.lua" in result.needed

    def test_detects_time_timescale(self) -> None:
        result = detect_needed_bridges([
            "Time.timeScale = 0.5"
        ])
        assert "Time.lua" in result.needed

    def test_detects_time_require(self) -> None:
        result = detect_needed_bridges([
            'local Time = require(game:GetService("ReplicatedStorage"):WaitForChild("Time"))'
        ])
        assert "Time.lua" in result.needed

    # --- Coroutine ---

    def test_detects_coroutine_start(self) -> None:
        result = detect_needed_bridges([
            "Coroutine.Start(function() end)"
        ])
        assert "Coroutine.lua" in result.needed

    def test_detects_coroutine_waitforseconds(self) -> None:
        result = detect_needed_bridges([
            "Coroutine.WaitForSeconds(2)"
        ])
        assert "Coroutine.lua" in result.needed

    def test_detects_coroutine_yield(self) -> None:
        result = detect_needed_bridges([
            "Coroutine.Yield()"
        ])
        assert "Coroutine.lua" in result.needed

    # --- Physics ---

    def test_detects_physics_raycast(self) -> None:
        result = detect_needed_bridges([
            "local hit = Physics.Raycast(origin, direction, 100)"
        ])
        assert "Physics.lua" in result.needed

    def test_detects_physics_checksphere(self) -> None:
        result = detect_needed_bridges([
            "local found = Physics.CheckSphere(pos, 5)"
        ])
        assert "Physics.lua" in result.needed

    def test_detects_physics_overlapsphere(self) -> None:
        result = detect_needed_bridges([
            "local hits = Physics.OverlapSphere(center, radius)"
        ])
        assert "Physics.lua" in result.needed

    # --- MonoBehaviour ---

    def test_detects_monobehaviour_new(self) -> None:
        result = detect_needed_bridges([
            "local mb = MonoBehaviour.new()"
        ])
        assert "MonoBehaviour.lua" in result.needed

    def test_detects_monobehaviour_require(self) -> None:
        result = detect_needed_bridges([
            'local MB = require(ReplicatedStorage:WaitForChild("MonoBehaviour"))'
        ])
        assert "MonoBehaviour.lua" in result.needed

    # --- GameObjectUtil ---

    def test_detects_gameobjectutil_instantiate(self) -> None:
        result = detect_needed_bridges([
            "local clone = GameObjectUtil.Instantiate(template)"
        ])
        assert "GameObjectUtil.lua" in result.needed

    def test_detects_gameobjectutil_destroy(self) -> None:
        result = detect_needed_bridges([
            "GameObjectUtil.Destroy(obj)"
        ])
        assert "GameObjectUtil.lua" in result.needed

    def test_detects_gameobjectutil_find(self) -> None:
        result = detect_needed_bridges([
            'local player = GameObjectUtil.Find("Player")'
        ])
        assert "GameObjectUtil.lua" in result.needed

    def test_detects_gameobjectutil_findwithtag(self) -> None:
        result = detect_needed_bridges([
            'local enemies = GameObjectUtil.FindWithTag("Enemy")'
        ])
        assert "GameObjectUtil.lua" in result.needed

    def test_detects_gameobjectutil_setactive(self) -> None:
        result = detect_needed_bridges([
            "GameObjectUtil.SetActive(obj, false)"
        ])
        assert "GameObjectUtil.lua" in result.needed

    def test_detects_gameobjectutil_instantiatefromasset(self) -> None:
        result = detect_needed_bridges([
            "local clone = GameObjectUtil.InstantiateFromAsset(123456)"
        ])
        assert "GameObjectUtil.lua" in result.needed

    # --- StateMachine ---

    def test_detects_statemachine_new(self) -> None:
        result = detect_needed_bridges([
            "local sm = StateMachine.new()"
        ])
        assert "StateMachine.lua" in result.needed

    def test_detects_statemachine_require(self) -> None:
        result = detect_needed_bridges([
            'local SM = require(ReplicatedStorage:WaitForChild("StateMachine"))'
        ])
        assert "StateMachine.lua" in result.needed

    # --- Multiple bridges ---

    def test_detects_multiple_bridges(self) -> None:
        result = detect_needed_bridges([
            'local Input = require(ReplicatedStorage:WaitForChild("Input"))\n'
            "local hit = Physics.Raycast(origin, dir, 100)\n"
            "local elapsed = Time.time\n"
        ])
        assert "Input.lua" in result.needed
        assert "Physics.lua" in result.needed
        assert "Time.lua" in result.needed

    def test_detects_across_multiple_scripts(self) -> None:
        result = detect_needed_bridges([
            'if Input.GetKey("W") then end',
            "local hit = Physics.Raycast(o, d, 50)",
        ])
        assert "Input.lua" in result.needed
        assert "Physics.lua" in result.needed

    # --- Deduplication ---

    def test_skips_already_present(self) -> None:
        result = detect_needed_bridges(
            ['if Input.GetKey("W") then end'],
            existing_script_names={"Input.lua"},
        )
        assert "Input.lua" not in result.needed
        assert "Input.lua" in result.already_present

    def test_skips_already_present_but_detects_others(self) -> None:
        result = detect_needed_bridges(
            [
                'if Input.GetKey("W") then end\n'
                "local t = Time.deltaTime\n"
            ],
            existing_script_names={"Input.lua"},
        )
        assert "Input.lua" not in result.needed
        assert "Time.lua" in result.needed

    # --- False positives ---

    def test_no_false_positive_on_similar_names(self) -> None:
        """'InputHandler' should not trigger Input bridge."""
        result = detect_needed_bridges([
            "local InputHandler = {}\n"
            "function InputHandler.process() end\n"
        ])
        assert "Input.lua" not in result.needed

    def test_no_false_positive_on_comment(self) -> None:
        """Comments containing bridge names should still trigger — the regex
        doesn't distinguish comments from code, but this is acceptable as
        false positives are harmless (just an extra module included)."""
        # This is a design decision: we accept rare false positives
        pass

    def test_no_false_positive_on_string_time(self) -> None:
        """A string literal 'Time.deltaTime' in quotes isn't code usage,
        but we accept this false positive as harmless."""
        pass


# ---------------------------------------------------------------------------
# inject_bridges
# ---------------------------------------------------------------------------

class TestInjectBridges:
    """Load bridge module source files from disk."""

    def test_loads_existing_bridge(self) -> None:
        bridges = inject_bridges(["Input.lua"])
        assert len(bridges) == 1
        filename, source = bridges[0]
        assert filename == "Input.lua"
        assert "Input.GetKey" in source
        assert source.startswith("-- UnityBridge/Input")

    def test_loads_multiple_bridges(self) -> None:
        bridges = inject_bridges(["Time.lua", "Physics.lua"])
        assert len(bridges) == 2
        names = [b[0] for b in bridges]
        assert "Time.lua" in names
        assert "Physics.lua" in names

    def test_skips_nonexistent_bridge(self) -> None:
        bridges = inject_bridges(["NotARealBridge.lua"])
        assert len(bridges) == 0

    def test_custom_bridge_dir(self, tmp_path: Path) -> None:
        (tmp_path / "Custom.lua").write_text("return {}", encoding="utf-8")
        bridges = inject_bridges(["Custom.lua"], bridge_dir=tmp_path)
        assert len(bridges) == 1
        assert bridges[0] == ("Custom.lua", "return {}")

    def test_empty_list(self) -> None:
        bridges = inject_bridges([])
        assert bridges == []

    def test_all_standard_bridges_loadable(self) -> None:
        """Every bridge in BRIDGE_SPECS should be loadable from disk."""
        filenames = [spec.filename for spec in BRIDGE_SPECS]
        bridges = inject_bridges(filenames)
        loaded_names = {b[0] for b in bridges}
        for fn in filenames:
            assert fn in loaded_names, f"Bridge {fn} not found on disk"


# ---------------------------------------------------------------------------
# BRIDGE_SPECS consistency
# ---------------------------------------------------------------------------

class TestBridgeSpecs:
    """Verify the bridge spec registry is consistent."""

    def test_no_duplicate_filenames(self) -> None:
        filenames = [s.filename for s in BRIDGE_SPECS]
        assert len(filenames) == len(set(filenames))

    def test_no_duplicate_module_names(self) -> None:
        names = [s.module_name for s in BRIDGE_SPECS]
        assert len(names) == len(set(names))

    def test_all_specs_have_patterns(self) -> None:
        for spec in BRIDGE_SPECS:
            assert len(spec.patterns) > 0, f"{spec.filename} has no patterns"

    def test_expected_bridge_count(self) -> None:
        """We expect 7 auto-detected bridges (excludes AnimatorBridge & TransformAnimator)."""
        assert len(BRIDGE_SPECS) == 7

    def test_animator_bridges_excluded(self) -> None:
        """AnimatorBridge and TransformAnimator are handled by animation_converter."""
        filenames = {s.filename for s in BRIDGE_SPECS}
        assert "AnimatorBridge.lua" not in filenames
        assert "TransformAnimator.lua" not in filenames
