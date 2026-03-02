"""Tests for modules/llm_cache.py."""

import json
import time

import pytest

from modules.llm_cache import CacheEntry, LLMCache


@pytest.fixture
def cache(tmp_path) -> LLMCache:
    """Create a cache instance with a temp directory."""
    return LLMCache(cache_dir=tmp_path / "cache", ttl_seconds=3600)


class TestLLMCache:
    """Tests for the LLMCache class."""

    def test_put_and_get(self, cache: LLMCache) -> None:
        cache.put("prompt1", "claude-opus-4-5", "response1")
        entry = cache.get("prompt1", "claude-opus-4-5")
        assert entry is not None
        assert entry.response == "response1"
        assert entry.model == "claude-opus-4-5"

    def test_cache_miss(self, cache: LLMCache) -> None:
        entry = cache.get("nonexistent", "model")
        assert entry is None

    def test_different_prompts_different_entries(self, cache: LLMCache) -> None:
        cache.put("prompt1", "model", "response1")
        cache.put("prompt2", "model", "response2")
        e1 = cache.get("prompt1", "model")
        e2 = cache.get("prompt2", "model")
        assert e1 is not None and e1.response == "response1"
        assert e2 is not None and e2.response == "response2"

    def test_different_models_different_entries(self, cache: LLMCache) -> None:
        cache.put("prompt", "model-a", "response-a")
        cache.put("prompt", "model-b", "response-b")
        ea = cache.get("prompt", "model-a")
        eb = cache.get("prompt", "model-b")
        assert ea is not None and ea.response == "response-a"
        assert eb is not None and eb.response == "response-b"

    def test_ttl_expiration(self, tmp_path) -> None:
        cache = LLMCache(cache_dir=tmp_path / "ttl", ttl_seconds=0.1)
        cache.put("prompt", "model", "response")
        # Should be fresh
        assert cache.get("prompt", "model") is not None
        # Wait for TTL to expire
        time.sleep(0.2)
        assert cache.get("prompt", "model") is None

    def test_stats_tracking(self, cache: LLMCache) -> None:
        cache.put("p1", "m", "r1")
        cache.get("p1", "m")  # hit
        cache.get("p2", "m")  # miss
        assert cache.stats.writes == 1
        assert cache.stats.hits == 1
        assert cache.stats.misses == 1

    def test_hit_rate(self, cache: LLMCache) -> None:
        cache.put("p1", "m", "r1")
        cache.get("p1", "m")
        cache.get("p2", "m")
        assert cache.stats.hit_rate == 0.5

    def test_clear(self, cache: LLMCache) -> None:
        cache.put("p1", "m", "r1")
        cache.put("p2", "m", "r2")
        assert cache.size == 2
        removed = cache.clear()
        assert removed == 2
        assert cache.size == 0
        assert cache.get("p1", "m") is None

    def test_evict_expired(self, tmp_path) -> None:
        cache = LLMCache(cache_dir=tmp_path / "evict", ttl_seconds=0.1)
        cache.put("p1", "m", "r1")
        time.sleep(0.2)
        cache.put("p2", "m", "r2")  # fresh
        evicted = cache.evict_expired()
        assert evicted == 1
        assert cache.get("p2", "m") is not None

    def test_disabled_cache(self, tmp_path) -> None:
        cache = LLMCache(cache_dir=tmp_path / "disabled", enabled=False)
        entry = cache.put("p1", "m", "r1")
        assert entry.response == "r1"  # put returns entry even when disabled
        assert cache.get("p1", "m") is None  # but get always misses

    def test_hash_deterministic(self) -> None:
        h1 = LLMCache.hash_prompt("same prompt", "same model")
        h2 = LLMCache.hash_prompt("same prompt", "same model")
        assert h1 == h2

    def test_hash_different_for_different_input(self) -> None:
        h1 = LLMCache.hash_prompt("prompt A", "model")
        h2 = LLMCache.hash_prompt("prompt B", "model")
        assert h1 != h2

    def test_stores_metadata(self, cache: LLMCache) -> None:
        cache.put(
            "prompt", "model", "response",
            confidence=0.85,
            warnings=["warn1"],
            token_input=100,
            token_output=200,
        )
        entry = cache.get("prompt", "model")
        assert entry is not None
        assert entry.confidence == 0.85
        assert entry.warnings == ["warn1"]
        assert entry.token_input == 100
        assert entry.token_output == 200

    def test_corrupt_entry_handled(self, cache: LLMCache) -> None:
        """Corrupt JSON on disk should not crash the cache."""
        h = LLMCache.hash_prompt("bad", "model")
        path = cache.cache_dir / f"{h}.json"
        path.write_text("NOT JSON", encoding="utf-8")
        entry = cache.get("bad", "model")
        assert entry is None
        assert not path.exists()  # should be cleaned up

    def test_size_property(self, cache: LLMCache) -> None:
        assert cache.size == 0
        cache.put("p1", "m", "r1")
        assert cache.size == 1
        cache.put("p2", "m", "r2")
        assert cache.size == 2


class TestCacheEntry:
    """Tests for the CacheEntry dataclass."""

    def test_frozen(self) -> None:
        entry = CacheEntry(
            prompt_hash="abc",
            model="m",
            response="r",
            confidence=0.9,
            warnings=[],
            timestamp=time.time(),
        )
        with pytest.raises(AttributeError):
            entry.response = "new"  # type: ignore[misc]
