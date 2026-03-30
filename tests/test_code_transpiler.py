"""Black-box tests for modules/code_transpiler.py."""

from pathlib import Path
from unittest.mock import patch

import pytest

from modules.code_transpiler import (
    TranspilationResult,
    TranspiledScript,
    transpile_scripts,
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
