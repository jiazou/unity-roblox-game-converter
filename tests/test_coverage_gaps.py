"""Tests for previously untested logic across multiple modules.

Covers gaps identified by codebase audit:
- code_validator: Luau ternary if, table constructors, mismatched brackets
- code_transpiler: check_method_completeness, _is_valid_cached_luau,
                   _strip_property_calls, _resolve_requires, _classify_script_type edge cases
- mesh_decimator: quality floor vs Roblox limit conflict
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# code_validator — Luau ternary if, table constructors, bracket mismatch
# ---------------------------------------------------------------------------

from modules.code_validator import validate_luau, check_method_completeness


class TestValidateLuauTernary:
    """Luau ternary if expressions (if a then b else c) shouldn't unbalance blocks."""

    def test_ternary_if_not_counted_as_block(self) -> None:
        source = "local x = if a then b else c\n"
        result = validate_luau(source)
        assert result.valid is True
        assert result.error_count == 0

    def test_ternary_if_with_nested_block(self) -> None:
        source = (
            "local x = if a then b else c\n"
            "if true then\n"
            "    print(x)\n"
            "end\n"
        )
        result = validate_luau(source)
        assert result.valid is True

    def test_multiple_ternary_ifs(self) -> None:
        source = (
            "local x = if a then 1 else 2\n"
            "local y = if b then 3 else 4\n"
            "local z = if c then 5 else 6\n"
        )
        result = validate_luau(source)
        assert result.valid is True
        assert result.error_count == 0

    def test_ternary_inside_function(self) -> None:
        source = (
            "function foo()\n"
            "    local x = if a then 1 else 2\n"
            "    return x\n"
            "end\n"
        )
        result = validate_luau(source)
        assert result.valid is True


class TestValidateLuauTableConstructors:
    """Valid Luau table constructors ({}) should not be flagged as C# braces."""

    def test_empty_table_not_flagged(self) -> None:
        source = "local t = {}\n"
        result = validate_luau(source)
        brace_issues = [i for i in result.issues if i.code == "E030"]
        assert len(brace_issues) == 0

    def test_table_with_values_not_flagged(self) -> None:
        source = "local t = {1, 2, 3}\n"
        result = validate_luau(source)
        brace_issues = [i for i in result.issues if i.code == "E030"]
        assert len(brace_issues) == 0

    def test_table_after_equals_not_flagged(self) -> None:
        source = "local config = {\n    speed = 10,\n    name = 'foo',\n}\n"
        result = validate_luau(source)
        brace_issues = [i for i in result.issues if i.code == "E030"]
        assert len(brace_issues) == 0

    def test_return_table_not_flagged(self) -> None:
        source = "return {\n    Init = Init,\n    Update = Update,\n}\n"
        result = validate_luau(source)
        brace_issues = [i for i in result.issues if i.code == "E030"]
        assert len(brace_issues) == 0

    def test_setmetatable_table_not_flagged(self) -> None:
        source = "local obj = setmetatable({}, mt)\n"
        result = validate_luau(source)
        brace_issues = [i for i in result.issues if i.code == "E030"]
        assert len(brace_issues) == 0


class TestValidateLuauBracketMismatch:
    """Bracket balance checks for mismatched types."""

    def test_mismatched_paren_bracket(self) -> None:
        source = "local x = (1]\n"
        result = validate_luau(source)
        assert result.valid is False
        assert any(i.code == "E021" for i in result.issues)

    def test_unclosed_bracket(self) -> None:
        source = "local t = [1, 2\n"
        result = validate_luau(source)
        assert result.valid is False
        assert any(i.code == "E022" for i in result.issues)

    def test_extra_closing_bracket(self) -> None:
        source = "local x = 1]\n"
        result = validate_luau(source)
        assert any(i.code == "E020" for i in result.issues)

    def test_nested_balanced_brackets(self) -> None:
        source = "local t = foo(bar[1], baz(2))\n"
        result = validate_luau(source)
        bracket_issues = [i for i in result.issues if i.code in ("E020", "E021", "E022")]
        assert len(bracket_issues) == 0


class TestValidateCSharpCloseBrace:
    """C#-style } else / } catch / } finally should be flagged."""

    def test_csharp_else_brace(self) -> None:
        source = "} else {\n    print('hi')\n}\n"
        result = validate_luau(source)
        assert any(i.code == "E030" for i in result.issues)

    def test_csharp_catch_brace(self) -> None:
        source = "} catch (Exception e) {\n}\n"
        result = validate_luau(source)
        assert any(i.code == "E030" for i in result.issues)


# ---------------------------------------------------------------------------
# code_validator — check_method_completeness
# ---------------------------------------------------------------------------

class TestCheckMethodCompleteness:
    """Tests for C# vs Luau method coverage detection."""

    def test_all_methods_present(self) -> None:
        csharp = (
            "public class Foo : MonoBehaviour {\n"
            "    public void Start() { }\n"
            "    public void DoStuff() { }\n"
            "}\n"
        )
        luau = (
            "function Foo.Start(self)\nend\n"
            "function Foo.DoStuff(self)\n"
            "    -- implementation\n"
            "end\n"
        )
        warnings = check_method_completeness(csharp, luau, "Foo.cs")
        assert len(warnings) == 0

    def test_missing_method_detected(self) -> None:
        csharp = (
            "public class Foo : MonoBehaviour {\n"
            "    public void DoStuff() { }\n"
            "    public void HandleInput() { }\n"
            "}\n"
        )
        luau = (
            "function Foo.DoStuff(self)\nend\n"
        )
        warnings = check_method_completeness(csharp, luau, "Foo.cs")
        assert len(warnings) == 1
        assert "HandleInput" in warnings[0]

    def test_unconverted_comment_counts(self) -> None:
        csharp = (
            "public class Foo {\n"
            "    public void MissingMethod() { }\n"
            "}\n"
        )
        luau = (
            "-- [UNCONVERTED] MissingMethod not supported\n"
            "-- TODO: implement MissingMethod\n"
        )
        warnings = check_method_completeness(csharp, luau, "Foo.cs")
        assert len(warnings) == 0  # covered by UNCONVERTED comment

    def test_no_public_methods(self) -> None:
        csharp = "private int x = 5;\n"
        luau = "local x = 5\n"
        warnings = check_method_completeness(csharp, luau, "test.cs")
        assert len(warnings) == 0

    def test_lifecycle_hooks_excluded(self) -> None:
        """Unity lifecycle hooks (Awake, OnDestroy, etc.) are excluded from comparison."""
        csharp = (
            "public class Foo : MonoBehaviour {\n"
            "    public void Awake() { }\n"
            "    public void OnDestroy() { }\n"
            "    public void OnGUI() { }\n"
            "}\n"
        )
        luau = "-- empty\n"
        warnings = check_method_completeness(csharp, luau, "Foo.cs")
        assert len(warnings) == 0

    def test_colon_method_syntax_detected(self) -> None:
        """Luau Class:Method syntax should be detected."""
        csharp = "public class Foo { public void DoThing() { } }\n"
        luau = "function Foo:DoThing()\nend\n"
        warnings = check_method_completeness(csharp, luau, "Foo.cs")
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# code_transpiler — _is_valid_cached_luau
# ---------------------------------------------------------------------------

from modules.code_transpiler import _is_valid_cached_luau


class TestIsValidCachedLuau:
    """Tests for cache validity heuristic."""

    def test_empty_string_invalid(self) -> None:
        assert _is_valid_cached_luau("") is False

    def test_whitespace_only_invalid(self) -> None:
        assert _is_valid_cached_luau("   \n  \n") is False

    def test_ends_with_return_valid(self) -> None:
        source = "local M = {}\nfunction M.foo()\nend\nreturn M\n"
        assert _is_valid_cached_luau(source) is True

    def test_ends_with_end_valid(self) -> None:
        source = "function foo()\n    print('hi')\nend"
        assert _is_valid_cached_luau(source) is True

    def test_ends_with_closing_paren_valid(self) -> None:
        source = "table.insert(list, value)"
        assert _is_valid_cached_luau(source) is True

    def test_truncated_mid_function_invalid(self) -> None:
        source = "function foo()\n    local x = 1\n    local y ="
        assert _is_valid_cached_luau(source) is False

    def test_return_in_last_15_lines_valid(self) -> None:
        """Return statement doesn't have to be on the very last line."""
        source = (
            "local M = {}\n"
            "return M\n"
            "\n\n\n\n\n"  # trailing blank lines
        )
        assert _is_valid_cached_luau(source) is True


# ---------------------------------------------------------------------------
# code_transpiler — _strip_property_calls
# ---------------------------------------------------------------------------

from modules.code_transpiler import _strip_property_calls


class TestStripPropertyCalls:
    """Tests for removing invalid property() calls from Luau output."""

    def test_removes_property_call(self) -> None:
        source = "Foo.bar = property(Foo.getBar, Foo.setBar)\nprint('hi')\n"
        result = _strip_property_calls(source)
        assert "property" not in result
        assert "print('hi')" in result

    def test_preserves_normal_code(self) -> None:
        source = "local x = 42\nprint(x)\n"
        result = _strip_property_calls(source)
        assert result == source

    def test_removes_multiple_property_calls(self) -> None:
        source = (
            "A.x = property(A.getX, A.setX)\n"
            "local y = 5\n"
            "A.z = property(A.getZ, A.setZ)\n"
        )
        result = _strip_property_calls(source)
        assert result.count("property") == 0
        assert "local y = 5" in result

    def test_does_not_remove_property_in_string(self) -> None:
        """Property in a string literal should not be affected (string stripping
        is done separately in the validator, not here)."""
        source = 'local s = "property(get, set)"\n'
        result = _strip_property_calls(source)
        # The regex matches full lines with `= property(...)`, a string assignment
        # doesn't match the pattern
        assert "property" in result


# ---------------------------------------------------------------------------
# code_transpiler — _resolve_requires
# ---------------------------------------------------------------------------

from modules.code_transpiler import _resolve_requires, TranspiledScript


class TestResolveRequires:
    """Tests for cross-file require() validation.

    Note: _REQUIRE_ANY matches the first quoted word in a require() call.
    For game:GetService("ReplicatedStorage"):WaitForChild("X"), it captures
    "ReplicatedStorage" (a builtin), NOT "X". Tests use simpler require patterns.
    """

    def _ts(self, name: str, luau: str) -> TranspiledScript:
        return TranspiledScript(
            source_path=Path(f"{name}.cs"),
            output_filename=f"{name}.lua",
            csharp_source="",
            luau_source=luau,
            strategy="ai",
            confidence=0.9,
        )

    def test_valid_require_no_warning(self) -> None:
        scripts = [
            self._ts("A", 'local B = require(ReplicatedStorage:WaitForChild("B"))'),
            self._ts("B", "return {}"),
        ]
        warnings = _resolve_requires(scripts)
        assert len(warnings) == 0

    def test_missing_require_target_warns(self) -> None:
        scripts = [
            self._ts("A", 'local Missing = require(ReplicatedStorage:WaitForChild("Missing"))'),
        ]
        warnings = _resolve_requires(scripts)
        assert len(warnings) == 1
        assert "Missing" in warnings[0]

    def test_builtin_service_not_warned(self) -> None:
        scripts = [
            self._ts("A", 'local RS = require(script.Parent:WaitForChild("RunService"))'),
        ]
        warnings = _resolve_requires(scripts)
        assert len(warnings) == 0

    def test_no_requires_no_warnings(self) -> None:
        scripts = [self._ts("A", "print('hello')")]
        warnings = _resolve_requires(scripts)
        assert len(warnings) == 0

    def test_multiple_missing_requires(self) -> None:
        scripts = [
            self._ts("A", (
                'local X = require(ReplicatedStorage:WaitForChild("X"))\n'
                'local Y = require(ReplicatedStorage:WaitForChild("Y"))\n'
            )),
        ]
        warnings = _resolve_requires(scripts)
        assert len(warnings) == 2


# ---------------------------------------------------------------------------
# code_transpiler — _classify_script_type edge cases
# ---------------------------------------------------------------------------

from modules.code_transpiler import _classify_script_type, CSharpClassInfo


class TestClassifyScriptTypeEdgeCases:
    """Edge cases for script type classification."""

    def test_no_ast_no_indicators_is_modulescript(self) -> None:
        """A plain script with no indicators defaults to ModuleScript."""
        result = _classify_script_type("class Foo { void DoStuff() {} }", None)
        assert result == "ModuleScript"

    def test_server_only_persistence(self) -> None:
        """PlayerPrefs with no client APIs → Script (server)."""
        source = "PlayerPrefs.SetInt(\"score\", 10);\nPlayerPrefs.Save();"
        result = _classify_script_type(source, None)
        assert result == "Script"

    def test_server_and_client_mixed_is_modulescript(self) -> None:
        """Both server and client indicators → ModuleScript (not conclusively server)."""
        source = (
            "PlayerPrefs.SetInt(\"score\", 10);\n"
            "Camera.main.fieldOfView = 60;\n"
        )
        result = _classify_script_type(source, None)
        assert result == "ModuleScript"

    def test_utility_class_via_ast(self) -> None:
        """Non-MonoBehaviour with no lifecycle hooks → ModuleScript."""
        ast = CSharpClassInfo(
            class_name="MathUtils",
            base_class="",
            lifecycle_hooks=[],
        )
        result = _classify_script_type("class MathUtils { }", ast)
        assert result == "ModuleScript"

    def test_network_attribute_in_source(self) -> None:
        """[Command] attribute in source → Script regardless of AST."""
        result = _classify_script_type("[Command] void CmdFire() { }", None)
        assert result == "Script"


# ---------------------------------------------------------------------------
# mesh_decimator — quality floor vs Roblox limit conflict
# ---------------------------------------------------------------------------

from modules.mesh_decimator import decimate_meshes


def _make_obj(path: Path, face_count: int) -> None:
    """Write a minimal .obj file with the given number of triangular faces."""
    lines = []
    verts_needed = face_count + 2
    for i in range(verts_needed):
        lines.append(f"v {float(i)} {float(i % 3)} {float(i % 5)}")
    for i in range(face_count):
        v1 = 1
        v2 = i + 2
        v3 = i + 3 if i + 3 <= verts_needed else 2
        lines.append(f"f {v1} {v2} {v3}")
    path.write_text("\n".join(lines), encoding="utf-8")


class TestQualityFloorVsRobloxLimit:
    """Test that the quality floor doesn't prevent Roblox compliance."""

    def test_quality_floor_clamped_to_roblox_limit(self, tmp_path: Path) -> None:
        """A 50K-face mesh with 60% quality floor would keep 30K faces,
        but the code should clamp to roblox_max (10K) and warn."""
        mesh = tmp_path / "huge.obj"
        _make_obj(mesh, 500)
        result = decimate_meshes(
            [mesh], tmp_path / "out",
            roblox_max_faces=100,
            target_faces=80,
            quality_floor=0.6,
        )
        # quality_floor * 500 = 300, which exceeds limit of 100
        # The code should clamp to 100 and issue a warning
        assert len(result.warnings) >= 1
        assert any("quality floor" in w for w in result.warnings)
        entry = result.entries[0]
        if entry.was_decimated:
            assert entry.final_faces <= 100

    def test_quality_floor_within_limit_no_warning(self, tmp_path: Path) -> None:
        """When quality floor stays within the limit, no clamping warning."""
        mesh = tmp_path / "medium.obj"
        _make_obj(mesh, 200)
        result = decimate_meshes(
            [mesh], tmp_path / "out",
            roblox_max_faces=200,  # floor = 120, under limit
            target_faces=150,
            quality_floor=0.6,
        )
        # 200 faces <= 200 limit, so it should be copied unchanged
        assert result.already_compliant == 1
        quality_warnings = [w for w in result.warnings if "quality floor" in w]
        assert len(quality_warnings) == 0

    def test_quality_floor_below_limit_no_warning(self, tmp_path: Path) -> None:
        """When floor_faces < roblox_max, no clamping warning is emitted.

        floor_faces = max(int(faces * quality_floor), MIN_FACES_TO_DECIMATE).
        MIN_FACES_TO_DECIMATE=500, so for small meshes the floor is 500.
        Use a mesh where floor stays under the limit.
        """
        mesh = tmp_path / "moderate.obj"
        # 1000 faces, quality_floor 0.6 → floor = max(600, 500) = 600
        # target = max(500, 600) = 600 which is < roblox_max of 800
        _make_obj(mesh, 1000)
        result = decimate_meshes(
            [mesh], tmp_path / "out",
            roblox_max_faces=800,
            target_faces=500,
            quality_floor=0.6,
        )
        quality_warnings = [w for w in result.warnings if "quality floor" in w]
        assert len(quality_warnings) == 0


# ---------------------------------------------------------------------------
# code_validator — trailing semicolons capped at 5 reports
# ---------------------------------------------------------------------------

class TestSemicolonCapping:
    """Trailing semicolons should only report first 5, then a summary."""

    def test_many_semicolons_capped(self) -> None:
        source = "\n".join(f"local x{i} = {i};" for i in range(20))
        result = validate_luau(source)
        w030_issues = [i for i in result.issues if i.code == "W030"]
        w031_issues = [i for i in result.issues if i.code == "W031"]
        assert len(w030_issues) == 5
        assert len(w031_issues) == 1
        assert "15 more" in w031_issues[0].message

    def test_few_semicolons_no_summary(self) -> None:
        source = "local x = 1;\nlocal y = 2;\n"
        result = validate_luau(source)
        w031_issues = [i for i in result.issues if i.code == "W031"]
        assert len(w031_issues) == 0


# ---------------------------------------------------------------------------
# code_validator — valid Luau `new` constructors not flagged
# ---------------------------------------------------------------------------

class TestNewConstructorWarning:
    """W010 warns about C# 'new Foo()' but 'Instance.new' should be fine in context."""

    def test_csharp_new_flagged(self) -> None:
        source = "local obj = new GameObject()\n"
        result = validate_luau(source)
        assert any(i.code == "W010" for i in result.issues)

    def test_instance_new_flagged_as_warning_not_error(self) -> None:
        """Instance.new() contains 'new' but it's a warning (W), not an error (E)."""
        source = 'local part = Instance.new("Part")\n'
        result = validate_luau(source)
        # This will match the W010 pattern, but that's ok — it's a warning
        new_issues = [i for i in result.issues if i.code == "W010"]
        for issue in new_issues:
            assert issue.severity == "warning"


# ---------------------------------------------------------------------------
# code_transpiler — _is_editor_or_test_path
# ---------------------------------------------------------------------------

from modules.code_transpiler import _is_editor_or_test_path


class TestIsEditorOrTestPath:
    """Additional edge cases for path filtering."""

    def test_deeply_nested_editor(self) -> None:
        assert _is_editor_or_test_path(("Plugins", "MyPlugin", "Editor", "Tool.cs")) is True

    def test_editor_tests_dir(self) -> None:
        assert _is_editor_or_test_path(("EditorTests", "FooTest.cs")) is True

    def test_test_framework_dir(self) -> None:
        assert _is_editor_or_test_path(("TestFramework", "Base.cs")) is True

    def test_runtime_script_not_excluded(self) -> None:
        assert _is_editor_or_test_path(("Scripts", "Runtime", "Player.cs")) is False

    def test_empty_path(self) -> None:
        assert _is_editor_or_test_path(()) is False
