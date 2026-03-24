"""Black-box tests for modules/code_transpiler.py."""

from pathlib import Path

import pytest

from modules.code_transpiler import (
    TranspilationResult,
    TranspiledScript,
    transpile_scripts,
)


class TestTranspileScripts:
    """Tests for the transpile_scripts() public API."""

    def test_returns_transpilation_result(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project)
        assert isinstance(result, TranspilationResult)

    def test_discovers_cs_files(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project)
        assert result.total >= 1

    def test_transpiled_script_fields(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project)
        ts = result.scripts[0]
        assert isinstance(ts, TranspiledScript)
        assert ts.source_path.suffix == ".cs"
        assert ts.output_filename.endswith(".lua")
        assert len(ts.csharp_source) > 0
        assert len(ts.luau_source) > 0

    def test_rule_based_strategy(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, use_ai=False)
        for ts in result.scripts:
            assert ts.strategy == "rule_based"

    def test_debug_log_converted(self, unity_project: Path) -> None:
        """Debug.Log should be converted to print."""
        result = transpile_scripts(unity_project, use_ai=False)
        ts = result.scripts[0]
        assert "print(" in ts.luau_source

    def test_variable_declaration_converted(self, unity_project: Path) -> None:
        """C# variable declarations should become 'local'."""
        result = transpile_scripts(unity_project, use_ai=False)
        ts = result.scripts[0]
        assert "local" in ts.luau_source

    def test_using_directives_stripped(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, use_ai=False)
        ts = result.scripts[0]
        assert "using UnityEngine" not in ts.luau_source

    def test_namespace_stripped(self, tmp_path: Path) -> None:
        project = tmp_path / "NS"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Test.cs").write_text(
            "namespace Foo {\n"
            "public class Bar : MonoBehaviour {\n"
            "    void Start() {\n"
            "        Debug.Log(\"hi\");\n"
            "    }\n"
            "}\n"
            "}\n",
            encoding="utf-8",
        )
        result = transpile_scripts(project, use_ai=False)
        ts = result.scripts[0]
        assert "namespace" not in ts.luau_source

    def test_confidence_score(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, use_ai=False)
        ts = result.scripts[0]
        assert 0.0 <= ts.confidence <= 1.0

    def test_flagged_below_threshold(self, tmp_path: Path) -> None:
        """A nearly-empty script may yield low confidence and get flagged."""
        project = tmp_path / "Low"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Empty.cs").write_text("// empty\n", encoding="utf-8")
        result = transpile_scripts(project, use_ai=False, confidence_threshold=0.99)
        ts = result.scripts[0]
        assert ts.flagged_for_review is True
        assert result.flagged >= 1

    def test_succeeded_count(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, use_ai=False, confidence_threshold=0.0)
        assert result.succeeded == result.total

    def test_output_filename_stem(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project)
        ts = result.scripts[0]
        assert ts.output_filename == ts.source_path.stem + ".lua"

    def test_missing_assets_dir_raises(self, tmp_path: Path) -> None:
        project = tmp_path / "NoAssets"
        project.mkdir()
        with pytest.raises(FileNotFoundError):
            transpile_scripts(project)

    def test_empty_assets_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "EmptyProject"
        (project / "Assets").mkdir(parents=True)
        result = transpile_scripts(project)
        assert result.total == 0
        assert result.scripts == []

    def test_curly_brace_warning(self, unity_project: Path) -> None:
        """Rule-based transpiler should warn about remaining braces."""
        result = transpile_scripts(unity_project, use_ai=False)
        ts = result.scripts[0]
        brace_warnings = [w for w in ts.warnings if "brace" in w.lower()]
        # If braces remain, there should be a warning
        if "{" in ts.luau_source or "}" in ts.luau_source:
            assert len(brace_warnings) > 0

    def test_multiple_scripts(self, tmp_path: Path) -> None:
        project = tmp_path / "Multi"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "A.cs").write_text("void Start() { Debug.Log(\"a\"); }\n", encoding="utf-8")
        (assets / "B.cs").write_text("void Start() { Debug.Log(\"b\"); }\n", encoding="utf-8")
        result = transpile_scripts(project)
        assert result.total == 2
        assert len(result.scripts) == 2

    def test_this_converted_to_self(self, tmp_path: Path) -> None:
        project = tmp_path / "SelfConvert"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "T.cs").write_text(
            "void Start() { this.speed = 1; }\n",
            encoding="utf-8",
        )
        result = transpile_scripts(project, use_ai=False)
        ts = result.scripts[0]
        assert "self." in ts.luau_source

    def test_ai_without_key_falls_back(self, unity_project: Path) -> None:
        """AI transpilation without API key should fall back to rule-based or handle gracefully."""
        result = transpile_scripts(unity_project, use_ai=True, api_key="")
        # Without API key, should use rule-based fallback
        for ts in result.scripts:
            assert ts.strategy == "rule_based"

    def test_coroutine_yield_return_null(self, tmp_path: Path) -> None:
        """yield return null should become task.wait()."""
        project = tmp_path / "Coroutine"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Spawner.cs").write_text(
            "using UnityEngine;\n"
            "using System.Collections;\n"
            "public class Spawner : MonoBehaviour {\n"
            "    IEnumerator SpawnLoop() {\n"
            "        while (true) {\n"
            "            Debug.Log(\"spawn\");\n"
            "            yield return null;\n"
            "        }\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        result = transpile_scripts(project, use_ai=False)
        ts = result.scripts[0]
        assert "task.wait()" in ts.luau_source

    def test_coroutine_wait_for_seconds(self, tmp_path: Path) -> None:
        """yield return new WaitForSeconds(n) should become task.wait(n)."""
        project = tmp_path / "WaitSecs"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Timer.cs").write_text(
            "using UnityEngine;\n"
            "using System.Collections;\n"
            "public class Timer : MonoBehaviour {\n"
            "    IEnumerator Countdown() {\n"
            "        yield return new WaitForSeconds(2.0f);\n"
            "        Debug.Log(\"done\");\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        result = transpile_scripts(project, use_ai=False)
        ts = result.scripts[0]
        assert "task.wait(" in ts.luau_source

    def test_event_subscription_connect(self, tmp_path: Path) -> None:
        """obj.OnClick += handler should become obj.OnClick:Connect(handler)."""
        project = tmp_path / "EventSub"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "UI.cs").write_text(
            "using UnityEngine;\n"
            "public class UI : MonoBehaviour {\n"
            "    void Start() {\n"
            "        button.OnClick += HandleClick;\n"
            "    }\n"
            "    void HandleClick() {\n"
            "        Debug.Log(\"clicked\");\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        result = transpile_scripts(project, use_ai=False)
        ts = result.scripts[0]
        assert "Connect" in ts.luau_source

    def test_string_interpolation(self, tmp_path: Path) -> None:
        """C# $\"text {expr}\" should become string.format."""
        project = tmp_path / "Interp"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Logger.cs").write_text(
            'using UnityEngine;\n'
            'public class Logger : MonoBehaviour {\n'
            '    void Start() {\n'
            '        string name = "World";\n'
            '        Debug.Log($"Hello {name}!");\n'
            '    }\n'
            '}\n',
            encoding="utf-8",
        )
        result = transpile_scripts(project, use_ai=False)
        ts = result.scripts[0]
        assert "string.format" in ts.luau_source


# ---------------------------------------------------------------------------
# Structural C# pattern detection
# ---------------------------------------------------------------------------

from modules.code_transpiler import _analyze_csharp_patterns


class TestAnalyzeCsharpPatterns:
    def test_custom_inheritance_warning(self) -> None:
        source = "public class PlayerController : Character {\n}"
        warnings = _analyze_csharp_patterns(source)
        assert any("extends custom base class" in w for w in warnings)
        assert any("Character" in w for w in warnings)

    def test_unity_base_class_no_warning(self) -> None:
        source = "public class Player : MonoBehaviour {\n}"
        warnings = _analyze_csharp_patterns(source)
        assert not any("extends custom base class" in w for w in warnings)

    def test_interface_not_flagged(self) -> None:
        source = "public class Player : MonoBehaviour, IDisposable {\n}"
        warnings = _analyze_csharp_patterns(source)
        assert not any("extends custom base class" in w for w in warnings)

    def test_linq_detection(self) -> None:
        source = "var enemies = players.Where(p => p.isEnemy).ToList();"
        warnings = _analyze_csharp_patterns(source)
        assert any("LINQ" in w for w in warnings)

    def test_no_linq_no_warning(self) -> None:
        source = "var x = GetComponent<Rigidbody>();"
        warnings = _analyze_csharp_patterns(source)
        assert not any("LINQ" in w for w in warnings)

    def test_network_attributes(self) -> None:
        source = "[Command]\nvoid CmdFire() { }\n[ClientRpc]\nvoid RpcDamage() { }"
        warnings = _analyze_csharp_patterns(source)
        assert any("Networking" in w for w in warnings)

    def test_complex_generics(self) -> None:
        source = "Dictionary<string, List<Vector3>> waypoints;"
        warnings = _analyze_csharp_patterns(source)
        assert any("generic" in w.lower() for w in warnings)

    def test_async_task(self) -> None:
        source = "async Task LoadLevel() { await Task.Delay(1000); }"
        warnings = _analyze_csharp_patterns(source)
        assert any("async" in w.lower() for w in warnings)

    def test_clean_script_no_warnings(self) -> None:
        source = (
            "public class Spinner : MonoBehaviour {\n"
            "    void Update() {\n"
            "        transform.Rotate(0, 1, 0);\n"
            "    }\n"
            "}\n"
        )
        warnings = _analyze_csharp_patterns(source)
        assert warnings == []
