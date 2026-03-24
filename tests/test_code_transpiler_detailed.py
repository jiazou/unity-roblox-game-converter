"""Fine-grained unit tests for modules/code_transpiler.py.

Tests script type classification, structural warnings, AI pipeline
integration, and edge cases.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from modules.code_transpiler import (
    TranspilationResult,
    TranspiledScript,
    _classify_script_type,
    _parse_csharp_ast,
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


class TestTranspileScriptsIntegration:
    """Integration tests for transpile_scripts with real file I/O."""

    @pytest.mark.usefixtures("_mock_ai")
    def test_subdirectory_scripts(self, tmp_path: Path) -> None:
        """Scripts in subdirectories of Assets/ should be found."""
        project = tmp_path / "SubDir"
        subdir = project / "Assets" / "Scripts" / "Player"
        subdir.mkdir(parents=True)
        (subdir / "Move.cs").write_text(
            "void Update() { Debug.Log(\"move\"); }", encoding="utf-8"
        )
        result = transpile_scripts(project, api_key="test-key")
        assert result.total == 1
        assert result.scripts[0].output_filename == "Move.lua"

    @pytest.mark.usefixtures("_mock_ai")
    def test_preserves_original_source(self, tmp_path: Path) -> None:
        project = tmp_path / "Pres"
        (project / "Assets").mkdir(parents=True)
        original = "using UnityEngine;\nvoid Start() { Debug.Log(\"hi\"); }\n"
        (project / "Assets" / "Keep.cs").write_text(original, encoding="utf-8")
        result = transpile_scripts(project, api_key="test-key")
        ts = result.scripts[0]
        assert ts.csharp_source == original

    @pytest.mark.usefixtures("_mock_ai")
    def test_complex_csharp_doesnt_crash(self, tmp_path: Path) -> None:
        """Complex C# should not crash the transpiler pipeline."""
        project = tmp_path / "Complex"
        (project / "Assets").mkdir(parents=True)
        code = (
            "using UnityEngine;\n"
            "using System.Collections.Generic;\n"
            "\n"
            "namespace Game.Player {\n"
            "    public class Controller : MonoBehaviour {\n"
            "        [SerializeField] float speed = 5.0f;\n"
            "        private List<int> scores = new List<int>();\n"
            "        void Start() { Debug.Log(\"Starting\"); }\n"
            "        void Update() { float dt = Time.deltaTime; }\n"
            "    }\n"
            "}\n"
        )
        (project / "Assets" / "Controller.cs").write_text(code, encoding="utf-8")
        result = transpile_scripts(project, api_key="test-key")
        assert result.total == 1

    @pytest.mark.usefixtures("_mock_ai")
    def test_output_filenames_unique(self, tmp_path: Path) -> None:
        project = tmp_path / "Unique"
        (project / "Assets").mkdir(parents=True)
        for name in ("Alpha", "Beta", "Gamma"):
            (project / "Assets" / f"{name}.cs").write_text(
                f"void Start() {{ Debug.Log(\"{name}\"); }}", encoding="utf-8"
            )
        result = transpile_scripts(project, api_key="test-key")
        filenames = [ts.output_filename for ts in result.scripts]
        assert len(filenames) == len(set(filenames))

    @pytest.mark.usefixtures("_mock_ai")
    def test_all_scripts_use_ai_strategy(self, tmp_path: Path) -> None:
        project = tmp_path / "Strat"
        (project / "Assets").mkdir(parents=True)
        (project / "Assets" / "A.cs").write_text("class A {}", encoding="utf-8")
        result = transpile_scripts(project, api_key="test-key")
        for ts in result.scripts:
            assert ts.strategy == "ai"


# ---------------------------------------------------------------------------
# Script type classification
# ---------------------------------------------------------------------------

_has_tree_sitter = False
try:
    import tree_sitter_c_sharp  # noqa: F401
    _has_tree_sitter = True
except ImportError:
    pass


@pytest.mark.skipif(not _has_tree_sitter, reason="tree-sitter-c-sharp not installed")
class TestClassifyScriptType:
    """Test _classify_script_type with AST info."""

    def test_utility_class_is_module_script(self) -> None:
        source = (
            "public class MathHelper {\n"
            "    public static float Clamp(float v, float min, float max) {\n"
            "        return Mathf.Clamp(v, min, max);\n"
            "    }\n"
            "}\n"
        )
        ast_info = _parse_csharp_ast(source)
        script_type = _classify_script_type(source, ast_info)
        assert script_type == "ModuleScript"

    def test_input_script_is_module_script(self) -> None:
        """Input-handling MonoBehaviours become ModuleScripts — the bootstrap drives them."""
        source = (
            "using UnityEngine;\n"
            "public class PlayerInput : MonoBehaviour {\n"
            "    void Update() {\n"
            "        if (Input.GetKeyDown(KeyCode.Space)) { }\n"
            "    }\n"
            "}\n"
        )
        ast_info = _parse_csharp_ast(source)
        script_type = _classify_script_type(source, ast_info)
        assert script_type == "ModuleScript"

    def test_server_script_is_script(self) -> None:
        source = (
            "using UnityEngine;\n"
            "public class SaveManager : MonoBehaviour {\n"
            "    void Start() {\n"
            "        PlayerPrefs.SetInt(\"score\", 100);\n"
            "        PlayerPrefs.Save();\n"
            "    }\n"
            "}\n"
        )
        ast_info = _parse_csharp_ast(source)
        script_type = _classify_script_type(source, ast_info)
        assert script_type == "Script"

    def test_monobehaviour_default_is_module_script(self) -> None:
        """MonoBehaviours without strong server signals become ModuleScripts."""
        source = (
            "using UnityEngine;\n"
            "public class Simple : MonoBehaviour {\n"
            "    void Start() { Debug.Log(\"hi\"); }\n"
            "}\n"
        )
        ast_info = _parse_csharp_ast(source)
        script_type = _classify_script_type(source, ast_info)
        assert script_type == "ModuleScript"
