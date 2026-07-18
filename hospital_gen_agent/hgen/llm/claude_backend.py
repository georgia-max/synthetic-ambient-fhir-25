"""Claude LLM backend — the single seam replacing the original gpt_structure.py.

Exposes ``llm()``: one text-in / text-out call through the Anthropic SDK, with an
on-disk cache and three modes selected by the ``HGEN_LLM_MODE`` env var:

* ``canned`` (default) — never touches the network; returns a deterministic stub
  (the per-prompt ``canned`` argument supplied by ``prompts.py``). This lets the
  whole cognition pipeline run offline with no API key.
* ``cache``  — return a cached completion on hit; call the live API on a miss and
  store the result.
* ``live``   — always call the live API and refresh the cache.

The module imports and runs with **no** ``ANTHROPIC_API_KEY`` set (canned mode);
the SDK is imported lazily so ``anthropic`` need not be installed for canned use.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from hgen.config import MODEL_SONNET  # re-exported default model

# hgen/.llm_cache/  (this file lives at hgen/llm/claude_backend.py)
CACHE_DIR = Path(__file__).resolve().parents[1] / ".llm_cache"

_MODES = {"live", "cache", "canned"}


def _mode() -> str:
    """Current backend mode from ``HGEN_LLM_MODE`` (unknown -> ``canned``)."""
    mode = os.environ.get("HGEN_LLM_MODE", "canned").strip().lower()
    return mode if mode in _MODES else "canned"


def _cache_path(model: str, prompt: str) -> Path:
    """On-disk cache path keyed by sha256(model + prompt)."""
    key = hashlib.sha256(f"{model}\x00{prompt}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.txt"


def _call_api(prompt: str, model: str, max_tokens: int) -> str:
    """Make one live Anthropic call and return the concatenated text blocks.

    Note: ``temperature`` is intentionally not sent — the target models
    (claude-sonnet-5 / claude-opus-4-8) reject sampling params with a 400.
    """
    import anthropic  # lazy: only needed for live/cache-miss calls

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the env
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()


def llm(
    prompt: str,
    model: str = MODEL_SONNET,
    max_tokens: int = 512,
    temperature: int = 0,
    *,
    canned: str | None = None,
) -> str:
    """Return a completion for ``prompt`` under the current ``HGEN_LLM_MODE``.

    ``temperature`` is accepted for interface compatibility but not forwarded to
    the API (the target models reject it). ``canned`` is the deterministic stub
    returned in canned mode (and as the offline fallback shape callers parse).
    """
    mode = _mode()
    if mode == "canned":
        return canned if canned is not None else ""

    path = _cache_path(model, prompt)
    if mode == "cache" and path.exists():
        return path.read_text(encoding="utf-8")

    # live, or cache-miss: call the API and refresh the cache.
    completion = _call_api(prompt, model, max_tokens)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(completion, encoding="utf-8")
    return completion


if __name__ == "__main__":  # tiny smoke test
    print("mode:", _mode())
    print("cache:", CACHE_DIR)
    print(llm("ping", canned="pong"))
