"""Black-box tests for modules/code_transpiler.py."""

from pathlib import Path
from unittest.mock import patch

import pytest

from modules.code_transpiler import (
    TranspilationResult,
    TranspiledScript,
    transpile_scripts,
    _extract_class_names,
    _extract_references,
    _build_dependency_graph,
    _topological_sort,
    _build_scoped_context,
)


# A mock that replaces _ai_transpile so tests don't need an API key.
_MOCK_LUAU = "-- mock luau output\nlocal module = {}\nreturn module\n"


def _fake_ai_transpile(csharp, api_key, model, max_tokens, **kwargs):
    return _MOCK_LUAU, 0.9, []


@pytest.fixture()
def _mock_ai():
    with patch("modules.code_transpiler._ai_transpile", side_effect=_fake_ai_transpile):
        yield


class TestTranspileScripts:
    """Tests for the transpile_scripts() public API."""

    @pytest.mark.usefixtures("_mock_ai")
    def test_returns_transpilation_result(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, api_key="test-key")
        assert isinstance(result, TranspilationResult)

    @pytest.mark.usefixtures("_mock_ai")
    def test_discovers_cs_files(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, api_key="test-key")
        assert result.total >= 1

    @pytest.mark.usefixtures("_mock_ai")
    def test_transpiled_script_fields(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, api_key="test-key")
        ts = result.scripts[0]
        assert isinstance(ts, TranspiledScript)
        assert ts.source_path.suffix == ".cs"
        assert ts.output_filename.endswith(".lua")
        assert len(ts.csharp_source) > 0
        assert len(ts.luau_source) > 0

    @pytest.mark.usefixtures("_mock_ai")
    def test_ai_strategy(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, api_key="test-key")
        for ts in result.scripts:
            assert ts.strategy == "ai"

    @pytest.mark.usefixtures("_mock_ai")
    def test_confidence_score(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, api_key="test-key")
        ts = result.scripts[0]
        assert 0.0 <= ts.confidence <= 1.0

    @pytest.mark.usefixtures("_mock_ai")
    def test_succeeded_count(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, api_key="test-key", confidence_threshold=0.0)
        assert result.succeeded == result.total

    @pytest.mark.usefixtures("_mock_ai")
    def test_output_filename_stem(self, unity_project: Path) -> None:
        result = transpile_scripts(unity_project, api_key="test-key")
        ts = result.scripts[0]
        assert ts.output_filename == ts.source_path.stem + ".lua"

    def test_missing_assets_dir_raises(self, tmp_path: Path) -> None:
        project = tmp_path / "NoAssets"
        project.mkdir()
        with pytest.raises(FileNotFoundError):
            transpile_scripts(project, api_key="test-key")

    @pytest.mark.usefixtures("_mock_ai")
    def test_empty_assets_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "EmptyProject"
        (project / "Assets").mkdir(parents=True)
        result = transpile_scripts(project, api_key="test-key")
        assert result.total == 0
        assert result.scripts == []

    @pytest.mark.usefixtures("_mock_ai")
    def test_multiple_scripts(self, tmp_path: Path) -> None:
        project = tmp_path / "Multi"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "A.cs").write_text("void Start() { Debug.Log(\"a\"); }\n", encoding="utf-8")
        (assets / "B.cs").write_text("void Start() { Debug.Log(\"b\"); }\n", encoding="utf-8")
        result = transpile_scripts(project, api_key="test-key")
        assert result.total == 2
        assert len(result.scripts) == 2

    @pytest.mark.usefixtures("_mock_ai")
    def test_flagged_on_low_confidence(self, tmp_path: Path) -> None:
        """Mock returns 0.9 confidence — threshold at 0.99 should flag it."""
        project = tmp_path / "Flag"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "A.cs").write_text("class A {}\n", encoding="utf-8")
        result = transpile_scripts(project, api_key="test-key", confidence_threshold=0.99)
        ts = result.scripts[0]
        assert ts.flagged_for_review is True
        assert result.flagged >= 1

    def test_ai_transpile_error_returns_commented_source(self, tmp_path: Path) -> None:
        """AI failure should produce commented-out C# as fallback."""
        project = tmp_path / "Err"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Fail.cs").write_text("class Fail {}\n", encoding="utf-8")
        # Use a fake key — _ai_transpile will fail due to invalid key
        result = transpile_scripts(project, api_key="invalid-key-xxx")
        ts = result.scripts[0]
        assert "AI transpilation failed" in ts.luau_source
        assert ts.confidence == 0.0


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

    # --- Object pooling ---

    def test_object_pool_generic(self) -> None:
        source = "ObjectPool<Bullet> bulletPool = new ObjectPool<Bullet>();"
        warnings = _analyze_csharp_patterns(source)
        assert any("pooling" in w.lower() for w in warnings)

    def test_pool_manager(self) -> None:
        source = "PoolManager.Spawn(prefab, position, rotation);"
        warnings = _analyze_csharp_patterns(source)
        assert any("pooling" in w.lower() for w in warnings)

    def test_pool_get_return(self) -> None:
        source = (
            "var bullet = pool.Get();\n"
            "pool.Return(bullet);\n"
        )
        warnings = _analyze_csharp_patterns(source)
        assert any("pooling" in w.lower() for w in warnings)

    def test_pool_release(self) -> None:
        source = "pool.Release(obj);"
        warnings = _analyze_csharp_patterns(source)
        assert any("pooling" in w.lower() for w in warnings)

    def test_pool_despawn(self) -> None:
        source = "PoolManager.Despawn(enemy);"
        warnings = _analyze_csharp_patterns(source)
        assert any("pooling" in w.lower() for w in warnings)

    def test_spawn_despawn_generic(self) -> None:
        """Spawn/Despawn on any object should trigger (common pool API)."""
        source = "manager.Spawn(prefab);\nmanager.Despawn(obj);"
        warnings = _analyze_csharp_patterns(source)
        assert any("pooling" in w.lower() for w in warnings)

    def test_no_pool_false_positive(self) -> None:
        """Regular method calls shouldn't trigger pooling detection."""
        source = "var item = inventory.Get(0);\nDebug.Log(item);"
        warnings = _analyze_csharp_patterns(source)
        assert not any("pooling" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Flagging for review — networking/pooling scripts
# ---------------------------------------------------------------------------

from modules.code_transpiler import _FLAG_FOR_REVIEW_MARKERS


class TestFlagForReviewMarkers:
    def test_networking_warning_is_flaggable(self) -> None:
        source = "[Command]\nvoid CmdFire() { }"
        warnings = _analyze_csharp_patterns(source)
        flaggable = any(
            marker in w
            for w in warnings
            for marker in _FLAG_FOR_REVIEW_MARKERS
        )
        assert flaggable

    def test_pooling_warning_is_flaggable(self) -> None:
        source = "ObjectPool<Bullet> pool;"
        warnings = _analyze_csharp_patterns(source)
        flaggable = any(
            marker in w
            for w in warnings
            for marker in _FLAG_FOR_REVIEW_MARKERS
        )
        assert flaggable

    def test_linq_warning_not_flaggable(self) -> None:
        """LINQ is annoying but the AI handles it reasonably — not flaggable."""
        source = "var x = list.Where(i => i > 0).ToList();"
        warnings = _analyze_csharp_patterns(source)
        flaggable = any(
            marker in w
            for w in warnings
            for marker in _FLAG_FOR_REVIEW_MARKERS
        )
        assert not flaggable

    def test_clean_script_not_flaggable(self) -> None:
        source = "public class Foo : MonoBehaviour { void Update() {} }"
        warnings = _analyze_csharp_patterns(source)
        flaggable = any(
            marker in w
            for w in warnings
            for marker in _FLAG_FOR_REVIEW_MARKERS
        )
        assert not flaggable


# ---------------------------------------------------------------------------
# Class name extraction
# ---------------------------------------------------------------------------


class TestExtractClassNames:
    def test_single_class(self) -> None:
        assert _extract_class_names("public class Player {}") == {"Player"}

    def test_multiple_types(self) -> None:
        source = "class Foo {}\nenum Bar {}\nstruct Baz {}\ninterface IQux {}"
        assert _extract_class_names(source) == {"Foo", "Bar", "Baz", "IQux"}

    def test_modifiers(self) -> None:
        source = "public abstract class Base {}\ninternal sealed class Derived {}"
        assert _extract_class_names(source) == {"Base", "Derived"}

    def test_no_types(self) -> None:
        assert _extract_class_names("int x = 5;") == set()

    def test_partial_class(self) -> None:
        assert _extract_class_names("public partial class Config {}") == {"Config"}


# ---------------------------------------------------------------------------
# Cross-file reference extraction
# ---------------------------------------------------------------------------


class TestExtractReferences:
    def test_finds_referenced_class(self) -> None:
        source = "class Controller { Player player; }"
        refs = _extract_references(source, {"Player", "Controller", "Enemy"})
        assert refs == {"Player"}

    def test_excludes_self_defined(self) -> None:
        source = "class Player { Player other; }"
        refs = _extract_references(source, {"Player"})
        assert refs == set()

    def test_multiple_refs(self) -> None:
        source = "class Game { Player p; Enemy e; }"
        refs = _extract_references(source, {"Player", "Enemy", "Game"})
        assert refs == {"Player", "Enemy"}

    def test_no_refs(self) -> None:
        source = "class Standalone { int x; }"
        refs = _extract_references(source, {"Player", "Enemy"})
        assert refs == set()

    def test_inheritance_ref(self) -> None:
        source = "class Dog : Animal { }"
        refs = _extract_references(source, {"Animal", "Dog"})
        assert refs == {"Animal"}


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------


class TestBuildDependencyGraph:
    def test_linear_deps(self) -> None:
        sources = {
            "Base": "public class Base { }",
            "Mid": "public class Mid : Base { }",
            "Top": "public class Top { Mid m; }",
        }
        graph, class_map = _build_dependency_graph(sources)
        assert graph["Base"] == set()
        assert graph["Mid"] == {"Base"}
        assert graph["Top"] == {"Mid"}
        assert class_map["Base"] == "Base"

    def test_no_deps(self) -> None:
        sources = {
            "A": "class A { }",
            "B": "class B { }",
        }
        graph, _ = _build_dependency_graph(sources)
        assert graph["A"] == set()
        assert graph["B"] == set()

    def test_mutual_deps(self) -> None:
        sources = {
            "Foo": "class Foo { Bar b; }",
            "Bar": "class Bar { Foo f; }",
        }
        graph, _ = _build_dependency_graph(sources)
        assert graph["Foo"] == {"Bar"}
        assert graph["Bar"] == {"Foo"}

    def test_multiple_classes_in_one_file(self) -> None:
        sources = {
            "Types": "enum Color {} struct Vec {}",
            "User": "class User { Color c; Vec v; }",
        }
        graph, class_map = _build_dependency_graph(sources)
        assert graph["User"] == {"Types"}
        assert class_map["Color"] == "Types"
        assert class_map["Vec"] == "Types"


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_linear_chain(self) -> None:
        graph = {"C": {"B"}, "B": {"A"}, "A": set()}
        order = _topological_sort(graph)
        assert order.index("A") < order.index("B") < order.index("C")

    def test_independent_nodes(self) -> None:
        graph = {"A": set(), "B": set(), "C": set()}
        order = _topological_sort(graph)
        assert set(order) == {"A", "B", "C"}

    def test_diamond(self) -> None:
        graph = {"D": {"B", "C"}, "B": {"A"}, "C": {"A"}, "A": set()}
        order = _topological_sort(graph)
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_cycle_doesnt_crash(self) -> None:
        graph = {"A": {"B"}, "B": {"A"}}
        order = _topological_sort(graph)
        assert set(order) == {"A", "B"}

    def test_empty_graph(self) -> None:
        assert _topological_sort({}) == []

    def test_single_node(self) -> None:
        assert _topological_sort({"X": set()}) == ["X"]


# ---------------------------------------------------------------------------
# Scoped context building
# ---------------------------------------------------------------------------


class TestBuildScopedContext:
    def test_includes_transpiled_luau_for_direct_dep(self) -> None:
        graph = {"App": {"Util"}, "Util": set()}
        sources = {"App": "class App { Util u; }", "Util": "class Util {}"}
        luau = {"Util": "local Util = {}\nreturn Util"}
        ctx = _build_scoped_context("App", graph, sources, luau)
        assert "Already-converted dependency: Util.lua" in ctx
        assert "local Util" in ctx

    def test_falls_back_to_csharp_for_unconverted_dep(self) -> None:
        graph = {"App": {"Util"}, "Util": set()}
        sources = {"App": "class App { Util u; }", "Util": "class Util {}"}
        ctx = _build_scoped_context("App", graph, sources, {})
        assert "Dependency (C# source): Util.cs" in ctx
        assert "class Util" in ctx

    def test_transitive_deps_get_summary_only(self) -> None:
        graph = {"Top": {"Mid"}, "Mid": {"Base"}, "Base": set()}
        sources = {
            "Top": "class Top { Mid m; }",
            "Mid": "class Mid : Base { public void DoStuff() {} }",
            "Base": "class Base { public void Init() {} }",
        }
        ctx = _build_scoped_context("Top", graph, sources, {})
        # Base is a transitive dep — should get a summary, not full source
        assert "Transitive ref: Base" in ctx
        assert "Init" in ctx

    def test_no_deps_returns_empty(self) -> None:
        graph = {"Solo": set()}
        sources = {"Solo": "class Solo {}"}
        assert _build_scoped_context("Solo", graph, sources, {}) == ""

    def test_prefers_luau_over_csharp(self) -> None:
        graph = {"A": {"B"}, "B": set()}
        sources = {"A": "class A { B b; }", "B": "class B { }"}
        luau = {"B": "-- converted B"}
        ctx = _build_scoped_context("A", graph, sources, luau)
        assert "Already-converted" in ctx
        assert "C# source" not in ctx


# ---------------------------------------------------------------------------
# Dependency-ordered transpilation (integration)
# ---------------------------------------------------------------------------


class TestDependencyOrderedTranspilation:
    """Verify transpile_scripts respects dependency order."""

    def test_deps_transpiled_before_dependents(self, tmp_path: Path) -> None:
        """Files with no deps should appear before files that reference them."""
        project = tmp_path / "DepOrder"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Base.cs").write_text(
            "public class Base { public void Init() {} }", encoding="utf-8"
        )
        (assets / "Derived.cs").write_text(
            "public class Derived : Base { public void Run() {} }", encoding="utf-8"
        )

        call_order: list[str] = []
        original_fake = _fake_ai_transpile

        def _tracking_transpile(csharp, api_key, model, max_tokens, **kwargs):
            filename = kwargs.get("target_filename", "")
            call_order.append(filename)
            return original_fake(csharp, api_key, model, max_tokens, **kwargs)

        with patch("modules.code_transpiler._ai_transpile", side_effect=_tracking_transpile):
            transpile_scripts(project, api_key="test-key")

        assert call_order.index("Base.cs") < call_order.index("Derived.cs")

    def test_scoped_context_passed_to_ai(self, tmp_path: Path) -> None:
        """Dependent file's prompt should contain dep's already-transpiled Luau."""
        project = tmp_path / "ScopedCtx"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        (assets / "Helper.cs").write_text(
            "public class Helper { public void Help() {} }", encoding="utf-8"
        )
        (assets / "Main.cs").write_text(
            "public class Main { Helper h; void Start() { h.Help(); } }",
            encoding="utf-8",
        )

        captured_contexts: dict[str, str] = {}

        def _capture_transpile(csharp, api_key, model, max_tokens, **kwargs):
            filename = kwargs.get("target_filename", "")
            ctx = kwargs.get("project_context", "")
            captured_contexts[filename] = ctx
            return _MOCK_LUAU, 0.9, []

        with patch("modules.code_transpiler._ai_transpile", side_effect=_capture_transpile):
            transpile_scripts(project, api_key="test-key")

        # Main.cs depends on Helper — its context should include Helper's Luau
        main_ctx = captured_contexts["Main.cs"]
        assert "Already-converted dependency: Helper.lua" in main_ctx

    def test_cached_luau_available_to_dependents(self, tmp_path: Path) -> None:
        """Cached scripts should still be fed as context to downstream files."""
        project = tmp_path / "CachedDep"
        assets = project / "Assets"
        assets.mkdir(parents=True)
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        (assets / "Lib.cs").write_text(
            "public class Lib { public int Compute() { return 1; } }",
            encoding="utf-8",
        )
        (assets / "App.cs").write_text(
            "public class App { Lib lib; void Run() { lib.Compute(); } }",
            encoding="utf-8",
        )
        # Pre-cache Lib
        cached_luau = "local Lib = {}\nfunction Lib:Compute() return 1 end\nreturn Lib\n"
        (cache_dir / "Lib.lua").write_text(cached_luau, encoding="utf-8")

        captured_contexts: dict[str, str] = {}

        def _capture_transpile(csharp, api_key, model, max_tokens, **kwargs):
            filename = kwargs.get("target_filename", "")
            captured_contexts[filename] = kwargs.get("project_context", "")
            return _MOCK_LUAU, 0.9, []

        with patch("modules.code_transpiler._ai_transpile", side_effect=_capture_transpile):
            transpile_scripts(
                project, api_key="test-key",
                transpile_cache_dir=str(cache_dir),
            )

        # Lib was cached so _ai_transpile shouldn't be called for it
        assert "Lib.cs" not in captured_contexts
        # App's context should include Lib's cached Luau
        app_ctx = captured_contexts["App.cs"]
        assert "Already-converted dependency: Lib.lua" in app_ctx
        assert "Lib:Compute" in app_ctx
