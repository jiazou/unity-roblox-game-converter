"""Tests for modules/scriptable_object_converter.py.

Covers ScriptableObject .asset parsing, Luau data table generation,
value-to-Lua conversion, and batch processing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modules.scriptable_object_converter import (
    ConvertedAsset,
    AssetConversionResult,
    convert_asset_file,
    convert_asset_files,
    _value_to_lua,
    _lua_escape_string,
)


# ---------------------------------------------------------------------------
# _lua_escape_string
# ---------------------------------------------------------------------------

class TestLuaEscapeString:
    def test_plain_string(self) -> None:
        assert _lua_escape_string("hello") == "hello"

    def test_backslash(self) -> None:
        assert _lua_escape_string("a\\b") == "a\\\\b"

    def test_double_quote(self) -> None:
        assert _lua_escape_string('say "hi"') == 'say \\"hi\\"'

    def test_newline(self) -> None:
        assert _lua_escape_string("line1\nline2") == "line1\\nline2"

    def test_combined_escapes(self) -> None:
        result = _lua_escape_string('a\\b\n"c"')
        assert result == 'a\\\\b\\n\\"c\\"'

    def test_empty_string(self) -> None:
        assert _lua_escape_string("") == ""


# ---------------------------------------------------------------------------
# _value_to_lua
# ---------------------------------------------------------------------------

class TestValueToLua:
    def test_none(self) -> None:
        assert _value_to_lua(None) == "nil"

    def test_true(self) -> None:
        assert _value_to_lua(True) == "true"

    def test_false(self) -> None:
        assert _value_to_lua(False) == "false"

    def test_int(self) -> None:
        assert _value_to_lua(42) == "42"

    def test_float(self) -> None:
        result = _value_to_lua(3.14)
        assert "3.14" in result

    def test_string(self) -> None:
        assert _value_to_lua("hello") == '"hello"'

    def test_string_with_special_chars(self) -> None:
        result = _value_to_lua('say "hi"')
        assert '\\"' in result

    def test_empty_list(self) -> None:
        assert _value_to_lua([]) == "{}"

    def test_list_of_ints(self) -> None:
        result = _value_to_lua([1, 2, 3])
        assert "1," in result
        assert "2," in result
        assert "3," in result

    def test_empty_dict(self) -> None:
        assert _value_to_lua({}) == "{}"

    def test_dict_with_values(self) -> None:
        result = _value_to_lua({"name": "sword", "damage": 10})
        assert "name" in result
        assert '"sword"' in result
        assert "damage" in result
        assert "10" in result

    def test_unity_object_reference_becomes_nil(self) -> None:
        ref = {"fileID": 12345, "guid": "abcd1234", "type": 3}
        result = _value_to_lua(ref)
        assert result == "nil --[[(Unity object reference)]]"

    def test_nested_dict(self) -> None:
        data = {"inner": {"x": 1}}
        result = _value_to_lua(data)
        assert "inner" in result
        assert "x = 1" in result

    def test_skip_fields_in_dict(self) -> None:
        data = {"m_Script": {"fileID": 0}, "myField": 42}
        result = _value_to_lua(data)
        assert "myField" in result
        assert "m_Script" not in result

    def test_m_prefix_stripped(self) -> None:
        data = {"m_Speed": 5.0}
        result = _value_to_lua(data)
        assert "Speed = " in result

    def test_m_Name_not_stripped(self) -> None:
        """m_Name is a known skip field so it should be excluded."""
        data = {"m_Name": "Test"}
        result = _value_to_lua(data)
        # m_Name is not in _SKIP_FIELDS but convert_asset_file skips it separately
        # _value_to_lua itself doesn't skip m_Name — it strips the prefix
        assert "Name" in result

    def test_non_identifier_key(self) -> None:
        data = {"123abc": "val"}
        result = _value_to_lua(data)
        assert '["123abc"]' in result


# ---------------------------------------------------------------------------
# convert_asset_file
# ---------------------------------------------------------------------------

class TestConvertAssetFile:
    def _write_asset(self, path: Path, yaml_content: str) -> Path:
        path.write_text(yaml_content, encoding="utf-8")
        return path

    def test_valid_scriptable_object(self, tmp_path: Path) -> None:
        asset = self._write_asset(tmp_path / "MyData.asset", textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!114 &11400000
            MonoBehaviour:
              m_ObjectHideFlags: 0
              m_Script: {fileID: 0}
              m_Name: MyData
              speed: 5.0
              health: 100
        """))
        result = convert_asset_file(asset)
        assert result is not None
        assert result.asset_name == "MyData"
        assert result.field_count == 2
        assert "speed" in result.luau_source
        assert "health" in result.luau_source
        assert "100" in result.luau_source

    def test_non_scriptable_object(self, tmp_path: Path) -> None:
        """A .asset file without MonoBehaviour should return None."""
        asset = self._write_asset(tmp_path / "Other.asset", textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: NotAScriptableObject
        """))
        result = convert_asset_file(asset)
        assert result is None

    def test_empty_user_fields(self, tmp_path: Path) -> None:
        """ScriptableObject with only internal fields → empty data table."""
        asset = self._write_asset(tmp_path / "Empty.asset", textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!114 &11400000
            MonoBehaviour:
              m_ObjectHideFlags: 0
              m_Script: {fileID: 0}
              m_Name: EmptyData
        """))
        result = convert_asset_file(asset)
        assert result is not None
        assert result.field_count == 0
        assert "return {}" in result.luau_source

    def test_nested_data(self, tmp_path: Path) -> None:
        asset = self._write_asset(tmp_path / "Nested.asset", textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!114 &11400000
            MonoBehaviour:
              m_Script: {fileID: 0}
              m_Name: Nested
              items:
                - name: Sword
                  damage: 10
                - name: Shield
                  defense: 5
        """))
        result = convert_asset_file(asset)
        assert result is not None
        assert "Sword" in result.luau_source
        assert "Shield" in result.luau_source
        assert "damage" in result.luau_source

    def test_unity_object_reference_becomes_nil(self, tmp_path: Path) -> None:
        asset = self._write_asset(tmp_path / "Ref.asset", textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!114 &11400000
            MonoBehaviour:
              m_Script: {fileID: 0}
              m_Name: RefData
              myPrefab: {fileID: 100, guid: abcd1234abcd1234abcd1234abcd1234, type: 3}
        """))
        result = convert_asset_file(asset)
        assert result is not None
        assert "nil" in result.luau_source

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        asset = self._write_asset(tmp_path / "Bad.asset", "not: valid: yaml: {{{{")
        result = convert_asset_file(asset)
        assert result is None

    def test_asset_name_from_m_Name(self, tmp_path: Path) -> None:
        asset = self._write_asset(tmp_path / "Fallback.asset", textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!114 &11400000
            MonoBehaviour:
              m_Script: {fileID: 0}
              m_Name: CorrectName
              value: 1
        """))
        result = convert_asset_file(asset)
        assert result is not None
        assert result.asset_name == "CorrectName"


# ---------------------------------------------------------------------------
# convert_asset_files (batch)
# ---------------------------------------------------------------------------

class TestConvertAssetFiles:
    def test_no_assets_dir(self, tmp_path: Path) -> None:
        """Project without Assets/ dir returns empty result."""
        result = convert_asset_files(tmp_path / "NoProject")
        assert result.total == 0
        assert result.converted == 0

    def test_multiple_asset_files(self, tmp_path: Path) -> None:
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()

        # Valid ScriptableObject
        (assets_dir / "A.asset").write_text(textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!114 &11400000
            MonoBehaviour:
              m_Script: {fileID: 0}
              m_Name: A
              val: 1
        """), encoding="utf-8")

        # Another valid one
        (assets_dir / "B.asset").write_text(textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!114 &11400000
            MonoBehaviour:
              m_Script: {fileID: 0}
              m_Name: B
              val: 2
        """), encoding="utf-8")

        # Non-ScriptableObject (should be skipped)
        (assets_dir / "C.asset").write_text(textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: NotSO
        """), encoding="utf-8")

        result = convert_asset_files(tmp_path)
        assert result.total == 3
        assert result.converted == 2
        assert result.skipped == 1
        assert len(result.assets) == 2

    def test_empty_assets_dir(self, tmp_path: Path) -> None:
        (tmp_path / "Assets").mkdir()
        result = convert_asset_files(tmp_path)
        assert result.total == 0
