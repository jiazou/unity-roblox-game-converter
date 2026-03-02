"""Tests for modules/api_mappings.py."""

from modules.api_mappings import (
    API_CALL_MAP,
    LIFECYCLE_MAP,
    SERVICE_IMPORTS,
    TYPE_MAP,
)


class TestAPICallMap:
    """Tests for the API_CALL_MAP dictionary."""

    def test_is_nonempty(self) -> None:
        assert len(API_CALL_MAP) > 100  # comprehensive mapping

    def test_debug_log_mapped(self) -> None:
        assert API_CALL_MAP["Debug.Log"] == "print"

    def test_debug_log_warning_mapped(self) -> None:
        assert API_CALL_MAP["Debug.LogWarning"] == "warn"

    def test_physics_raycast(self) -> None:
        assert "Raycast" in API_CALL_MAP["Physics.Raycast"]

    def test_instantiate(self) -> None:
        assert "Clone" in API_CALL_MAP["Instantiate"]

    def test_destroy(self) -> None:
        assert "Destroy" in API_CALL_MAP["Destroy"]

    def test_transform_position(self) -> None:
        assert "Position" in API_CALL_MAP["transform.position"]

    def test_get_component(self) -> None:
        assert "FindFirstChildOfClass" in API_CALL_MAP["GetComponent"]

    def test_time_deltatime(self) -> None:
        assert API_CALL_MAP["Time.deltaTime"] == "dt"

    def test_mathf_abs(self) -> None:
        assert API_CALL_MAP["Mathf.Abs"] == "math.abs"

    def test_vector3_new(self) -> None:
        assert API_CALL_MAP["new Vector3"] == "Vector3.new"

    def test_camera_main(self) -> None:
        assert "CurrentCamera" in API_CALL_MAP["Camera.main"]

    def test_start_coroutine(self) -> None:
        assert "task.spawn" in API_CALL_MAP["StartCoroutine"]

    def test_input_getkey(self) -> None:
        assert "UserInputService" in API_CALL_MAP["Input.GetKey"]

    def test_all_values_are_strings(self) -> None:
        for key, val in API_CALL_MAP.items():
            assert isinstance(key, str), f"Key {key!r} is not a string"
            assert isinstance(val, str), f"Value for {key!r} is not a string"


class TestTypeMap:
    """Tests for the TYPE_MAP dictionary."""

    def test_int_to_number(self) -> None:
        assert TYPE_MAP["int"] == "number"

    def test_bool_to_boolean(self) -> None:
        assert TYPE_MAP["bool"] == "boolean"

    def test_string_to_string(self) -> None:
        assert TYPE_MAP["string"] == "string"

    def test_vector3_preserved(self) -> None:
        assert TYPE_MAP["Vector3"] == "Vector3"

    def test_quaternion_to_cframe(self) -> None:
        assert TYPE_MAP["Quaternion"] == "CFrame"

    def test_gameobject_to_instance(self) -> None:
        assert TYPE_MAP["GameObject"] == "Instance"


class TestLifecycleMap:
    """Tests for the LIFECYCLE_MAP dictionary."""

    def test_update_uses_heartbeat(self) -> None:
        assert "Heartbeat" in LIFECYCLE_MAP["Update"]

    def test_fixed_update_uses_stepped(self) -> None:
        assert "Stepped" in LIFECYCLE_MAP["FixedUpdate"]

    def test_on_destroy(self) -> None:
        assert "Destroying" in LIFECYCLE_MAP["OnDestroy"]

    def test_on_collision_enter(self) -> None:
        assert "Touched" in LIFECYCLE_MAP["OnCollisionEnter"]

    def test_all_hooks_present(self) -> None:
        expected = {
            "Awake", "Start", "Update", "FixedUpdate", "LateUpdate",
            "OnEnable", "OnDisable", "OnDestroy",
            "OnCollisionEnter", "OnCollisionExit",
            "OnTriggerEnter", "OnTriggerExit",
        }
        for hook in expected:
            assert hook in LIFECYCLE_MAP, f"Missing lifecycle hook: {hook}"


class TestServiceImports:
    """Tests for the SERVICE_IMPORTS dictionary."""

    def test_runservice(self) -> None:
        assert 'GetService("RunService")' in SERVICE_IMPORTS["RunService"]

    def test_userinputservice(self) -> None:
        assert "UserInputService" in SERVICE_IMPORTS["UserInputService"]

    def test_all_are_local_assignments(self) -> None:
        for svc, line in SERVICE_IMPORTS.items():
            assert line.startswith("local "), f"{svc} import doesn't start with 'local'"
