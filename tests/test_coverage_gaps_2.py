"""Tests for previously untested logic — batch 2.

Covers:
- rbxl_binary_writer: zigzag, float rotation, interleave, string encoding
- conversion_helpers: quaternion math, world transform, bootstrap generation
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# rbxl_binary_writer — encoding helpers
# ---------------------------------------------------------------------------

from modules.rbxl_binary_writer import (
    _zigzag_i32,
    _rotate_float_bits,
    _interleave_u32,
    _encode_string,
    _write_chunk,
)


class TestZigzagI32:
    """ZigZag encoding maps signed integers to unsigned (for better compression)."""

    def test_zero(self) -> None:
        assert _zigzag_i32(0) == 0

    def test_positive(self) -> None:
        # ZigZag: 1 → 2, 2 → 4, 3 → 6
        assert _zigzag_i32(1) == 2
        assert _zigzag_i32(2) == 4
        assert _zigzag_i32(3) == 6

    def test_negative(self) -> None:
        # ZigZag: -1 → 1, -2 → 3, -3 → 5
        assert _zigzag_i32(-1 & 0xFFFFFFFF) == 1
        assert _zigzag_i32(-2 & 0xFFFFFFFF) == 3

    def test_large_positive(self) -> None:
        result = _zigzag_i32(1000)
        assert result == 2000

    def test_max_i32(self) -> None:
        # 2^31 - 1 = 2147483647 → zigzag = 4294967294
        result = _zigzag_i32(0x7FFFFFFF)
        assert result == 0xFFFFFFFE


class TestRotateFloatBits:
    """Float bit rotation for better LZ4 compression."""

    def test_zero(self) -> None:
        result = _rotate_float_bits(0.0)
        assert result == 0

    def test_one(self) -> None:
        # IEEE-754: 1.0 = 0x3F800000
        # Rotated left 1: (0x3F800000 << 1 | 0x3F800000 >> 31) & 0xFFFFFFFF
        bits = struct.unpack(">I", struct.pack(">f", 1.0))[0]  # 0x3F800000
        expected = ((bits << 1) | (bits >> 31)) & 0xFFFFFFFF
        assert _rotate_float_bits(1.0) == expected

    def test_negative_one(self) -> None:
        result = _rotate_float_bits(-1.0)
        # Should be a valid uint32
        assert 0 <= result <= 0xFFFFFFFF

    def test_roundtrip_concept(self) -> None:
        """The rotation is invertible — verifying the concept works."""
        for val in [0.0, 1.0, -1.0, 3.14, 100.5]:
            rotated = _rotate_float_bits(val)
            # Unrotate: shift right 1 | high bit
            unrotated = ((rotated >> 1) | (rotated << 31)) & 0xFFFFFFFF
            recovered = struct.unpack(">f", struct.pack(">I", unrotated))[0]
            assert recovered == pytest.approx(val)


class TestInterleaveU32:
    """Byte-interleaving for delta-compressed property arrays."""

    def test_single_value(self) -> None:
        result = _interleave_u32([0x01020304])
        # Single value: bytes are [01, 02, 03, 04]
        # Interleaved with n=1: byte0[val0], byte1[val0], byte2[val0], byte3[val0]
        assert result == bytes([0x01, 0x02, 0x03, 0x04])

    def test_two_values(self) -> None:
        result = _interleave_u32([0xAABBCCDD, 0x11223344])
        # n=2: byte0 of both vals, then byte1 of both, etc.
        expected = bytes([
            0xAA, 0x11,  # byte 0 of each
            0xBB, 0x22,  # byte 1 of each
            0xCC, 0x33,  # byte 2 of each
            0xDD, 0x44,  # byte 3 of each
        ])
        assert result == expected

    def test_empty(self) -> None:
        result = _interleave_u32([])
        assert result == b""

    def test_all_zeros(self) -> None:
        result = _interleave_u32([0, 0, 0])
        assert result == bytes(12)  # 3 * 4 = 12 zero bytes


class TestEncodeString:
    """Length-prefixed UTF-8 string encoding."""

    def test_empty_string(self) -> None:
        result = _encode_string("")
        assert result == struct.pack("<I", 0)

    def test_ascii_string(self) -> None:
        result = _encode_string("hello")
        assert result == struct.pack("<I", 5) + b"hello"

    def test_unicode_string(self) -> None:
        result = _encode_string("héllo")
        encoded = "héllo".encode("utf-8")
        assert result == struct.pack("<I", len(encoded)) + encoded


class TestWriteChunk:
    """Chunk frame construction with optional LZ4 compression."""

    def test_uncompressed_small_data(self) -> None:
        # Very small data may not benefit from compression
        result = _write_chunk(b"TEST", b"hi")
        # Header: 4 name + 4 compressed_len + 4 uncompressed_len + 4 reserved
        assert result[:4] == b"TEST"
        # Either compressed or uncompressed depending on whether lz4 helps
        assert len(result) >= 16 + 2

    def test_no_compress_flag(self) -> None:
        result = _write_chunk(b"META", b"data", compress=False)
        assert result[:4] == b"META"
        compressed_len = struct.unpack_from("<I", result, 4)[0]
        assert compressed_len == 0  # 0 signals uncompressed
        uncompressed_len = struct.unpack_from("<I", result, 8)[0]
        assert uncompressed_len == 4
        assert result[16:] == b"data"

    def test_empty_data(self) -> None:
        result = _write_chunk(b"EMPT", b"", compress=True)
        assert result[:4] == b"EMPT"
        # Empty data: compressed_len = 0, uncompressed_len = 0
        compressed_len = struct.unpack_from("<I", result, 4)[0]
        uncompressed_len = struct.unpack_from("<I", result, 8)[0]
        assert compressed_len == 0
        assert uncompressed_len == 0


# ---------------------------------------------------------------------------
# conversion_helpers — quaternion math
# ---------------------------------------------------------------------------

from modules.conversion_helpers import (
    _quat_multiply,
    _quat_rotate,
    _compute_world_transform,
)


class TestQuatMultiply:
    """Quaternion multiplication (Hamilton product)."""

    def test_identity_times_identity(self) -> None:
        identity = (0, 0, 0, 1)
        result = _quat_multiply(identity, identity)
        assert result == pytest.approx((0, 0, 0, 1))

    def test_identity_times_rotation(self) -> None:
        identity = (0, 0, 0, 1)
        rot = (0.5, 0.5, 0.5, 0.5)  # 120° rotation
        result = _quat_multiply(identity, rot)
        assert result == pytest.approx(rot)

    def test_rotation_times_identity(self) -> None:
        identity = (0, 0, 0, 1)
        rot = (0.5, 0.5, 0.5, 0.5)
        result = _quat_multiply(rot, identity)
        assert result == pytest.approx(rot)

    def test_90_degree_y_rotation(self) -> None:
        """90° around Y axis: q = (0, sin(45°), 0, cos(45°))."""
        s = math.sin(math.pi / 4)
        c = math.cos(math.pi / 4)
        q = (0, s, 0, c)
        # q * q should give 180° around Y
        result = _quat_multiply(q, q)
        assert result[0] == pytest.approx(0, abs=1e-10)
        assert result[1] == pytest.approx(1, abs=1e-10)  # sin(90°)
        assert result[2] == pytest.approx(0, abs=1e-10)
        assert result[3] == pytest.approx(0, abs=1e-10)  # cos(90°)


class TestQuatRotate:
    """Quaternion rotation of a 3D vector."""

    def test_identity_rotation(self) -> None:
        identity = (0, 0, 0, 1)
        v = (1, 2, 3)
        result = _quat_rotate(identity, v)
        assert result == pytest.approx(v)

    def test_180_y_rotation(self) -> None:
        """180° around Y should negate X and Z, keep Y."""
        q = (0, 1, 0, 0)  # 180° around Y
        v = (1, 2, 3)
        result = _quat_rotate(q, v)
        assert result[0] == pytest.approx(-1, abs=1e-10)
        assert result[1] == pytest.approx(2, abs=1e-10)
        assert result[2] == pytest.approx(-3, abs=1e-10)

    def test_90_y_rotation(self) -> None:
        """90° around Y should map (1,0,0) to (0,0,-1)."""
        s = math.sin(math.pi / 4)
        c = math.cos(math.pi / 4)
        q = (0, s, 0, c)
        v = (1, 0, 0)
        result = _quat_rotate(q, v)
        assert result[0] == pytest.approx(0, abs=1e-10)
        assert result[1] == pytest.approx(0, abs=1e-10)
        assert result[2] == pytest.approx(-1, abs=1e-10)


class TestComputeWorldTransform:
    """World transform composition (position + rotation)."""

    def test_identity_parent(self) -> None:
        identity = (0, 0, 0, 1)
        pos = (5, 10, 15)
        result_pos, result_rot = _compute_world_transform(pos, identity, (0, 0, 0), identity)
        assert result_pos == pytest.approx(pos)
        assert result_rot == pytest.approx(identity)

    def test_translation_only(self) -> None:
        identity = (0, 0, 0, 1)
        parent_pos = (10, 20, 30)
        local_pos = (1, 2, 3)
        result_pos, _ = _compute_world_transform(local_pos, identity, parent_pos, identity)
        assert result_pos == pytest.approx((11, 22, 33))

    def test_parent_rotation_affects_child_position(self) -> None:
        """Parent rotated 180° around Y should flip child's X and Z."""
        parent_rot = (0, 1, 0, 0)  # 180° around Y
        identity = (0, 0, 0, 1)
        local_pos = (1, 0, 0)
        result_pos, _ = _compute_world_transform(local_pos, identity, (0, 0, 0), parent_rot)
        assert result_pos[0] == pytest.approx(-1, abs=1e-10)
        assert result_pos[1] == pytest.approx(0, abs=1e-10)
        assert result_pos[2] == pytest.approx(0, abs=1e-10)


# ---------------------------------------------------------------------------
# conversion_helpers — generate_bootstrap_script (None path)
# ---------------------------------------------------------------------------

from modules.conversion_helpers import generate_bootstrap_script
from modules import scene_parser, guid_resolver, code_transpiler


class TestGenerateBootstrapScript:
    """Test bootstrap script generation edge cases."""

    def test_returns_none_for_empty_scenes(self, tmp_path: Path) -> None:
        """No scenes → no GameManager → returns None."""
        gi = guid_resolver.GuidIndex(project_root=tmp_path)
        tr = code_transpiler.TranspilationResult()
        result = generate_bootstrap_script([], gi, tr)
        assert result is None

    def test_returns_none_for_no_game_manager(self, tmp_path: Path) -> None:
        """Scenes without a GameManager MonoBehaviour → returns None."""
        node = scene_parser.SceneNode(
            name="MainCamera",
            file_id="1",
            active=True,
            layer=0,
            tag="MainCamera",
            components=[],
        )
        scene = scene_parser.ParsedScene(
            scene_path=Path("test.unity"),
            roots=[node],
            all_nodes={"1": node},
        )
        gi = guid_resolver.GuidIndex(project_root=tmp_path)
        tr = code_transpiler.TranspilationResult()
        result = generate_bootstrap_script([scene], gi, tr)
        assert result is None
