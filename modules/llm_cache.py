"""
llm_cache.py — Hash-based disk cache for LLM responses.

Caches LLM API responses keyed by a SHA-256 hash of the prompt content,
avoiding redundant API calls during iterative development (re-running
the converter on the same project).

Cache entries are JSON files stored in a configurable directory.
Staleness is controlled by a TTL (time-to-live) in seconds.

No other module is imported here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheEntry:
    """A single cached LLM response."""
    prompt_hash: str
    model: str
    response: str
    confidence: float
    warnings: list[str]
    timestamp: float       # time.time() when cached
    token_input: int = 0   # approximate input token count
    token_output: int = 0  # approximate output token count


@dataclass
class CacheStats:
    """Aggregate statistics for cache operations in a session."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    writes: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class LLMCache:
    """
    Disk-backed LLM response cache.

    Each cache entry is stored as a JSON file named by the prompt hash.
    Entries older than `ttl_seconds` are considered stale and discarded.

    Args:
        cache_dir: Directory where cache files are stored.
        ttl_seconds: Time-to-live for cache entries (default 7 days).
        enabled: If False, all operations are no-ops (pass-through mode).
    """

    def __init__(
        self,
        cache_dir: str | Path = ".cache/llm",
        ttl_seconds: float = 7 * 24 * 3600,  # 7 days
        enabled: bool = True,
    ) -> None:
        self.cache_dir = Path(cache_dir).resolve()
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self.stats = CacheStats()

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def hash_prompt(prompt: str, model: str = "") -> str:
        """
        Generate a deterministic hash for a prompt + model combination.

        The hash includes both the prompt content and the model name so that
        the same prompt sent to different models produces different cache keys.
        """
        content = f"{model}::{prompt}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _entry_path(self, prompt_hash: str) -> Path:
        """Get the file path for a cache entry."""
        return self.cache_dir / f"{prompt_hash}.json"

    def get(self, prompt: str, model: str = "") -> CacheEntry | None:
        """
        Look up a cached response for the given prompt.

        Returns None on miss or if the entry has expired.
        """
        if not self.enabled:
            self.stats.misses += 1
            return None

        prompt_hash = self.hash_prompt(prompt, model)
        path = self._entry_path(prompt_hash)

        if not path.exists():
            self.stats.misses += 1
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = CacheEntry(
                prompt_hash=data["prompt_hash"],
                model=data["model"],
                response=data["response"],
                confidence=data["confidence"],
                warnings=data.get("warnings", []),
                timestamp=data["timestamp"],
                token_input=data.get("token_input", 0),
                token_output=data.get("token_output", 0),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("llm_cache: corrupt entry %s: %s", prompt_hash[:12], exc)
            path.unlink(missing_ok=True)
            self.stats.misses += 1
            return None

        # Check TTL
        age = time.time() - entry.timestamp
        if age > self.ttl_seconds:
            logger.debug("llm_cache: expired entry %s (age=%.0fs)", prompt_hash[:12], age)
            path.unlink(missing_ok=True)
            self.stats.evictions += 1
            self.stats.misses += 1
            return None

        self.stats.hits += 1
        logger.debug("llm_cache: HIT %s", prompt_hash[:12])
        return entry

    def put(
        self,
        prompt: str,
        model: str,
        response: str,
        confidence: float = 0.9,
        warnings: list[str] | None = None,
        token_input: int = 0,
        token_output: int = 0,
    ) -> CacheEntry:
        """
        Store an LLM response in the cache.

        Returns the created CacheEntry.
        """
        prompt_hash = self.hash_prompt(prompt, model)
        entry = CacheEntry(
            prompt_hash=prompt_hash,
            model=model,
            response=response,
            confidence=confidence,
            warnings=warnings or [],
            timestamp=time.time(),
            token_input=token_input,
            token_output=token_output,
        )

        if not self.enabled:
            return entry

        path = self._entry_path(prompt_hash)
        try:
            path.write_text(
                json.dumps(asdict(entry), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stats.writes += 1
            logger.debug("llm_cache: WRITE %s", prompt_hash[:12])
        except OSError as exc:
            logger.warning("llm_cache: write failed for %s: %s", prompt_hash[:12], exc)

        return entry

    def clear(self) -> int:
        """
        Remove all cache entries.

        Returns the number of entries removed.
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        count = 0
        for path in self.cache_dir.glob("*.json"):
            path.unlink(missing_ok=True)
            count += 1

        logger.info("llm_cache: cleared %d entries", count)
        return count

    def evict_expired(self) -> int:
        """
        Remove entries older than TTL.

        Returns the number of entries evicted.
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        now = time.time()
        evicted = 0
        for path in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if now - data.get("timestamp", 0) > self.ttl_seconds:
                    path.unlink(missing_ok=True)
                    evicted += 1
            except (json.JSONDecodeError, OSError):
                path.unlink(missing_ok=True)
                evicted += 1

        self.stats.evictions += evicted
        return evicted

    @property
    def size(self) -> int:
        """Number of entries currently in the cache."""
        if not self.cache_dir.exists():
            return 0
        return len(list(self.cache_dir.glob("*.json")))
