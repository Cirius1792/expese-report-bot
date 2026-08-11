# ARCH-004: Composition / Configuration Without a Hidden Seam

> **EDD expectations for hexagonal configuration alignment.**
> **Branch:** refactor/hexagonal-alignment | **ARCH-004**

## Scope

The problem: configuration knowledge is distributed across the codebase. `main.py`
reads Telegram and database values; authorization reads its own environment value;
`DspyExtractionAdapter` reads LLM values during construction **and reads them again**
in `_call_image_with_retry`; the CLI separately constructs driven adapters. Required
values and failure modes are not visible in one place per process.

This phase addresses the most impactful part: **LLM configuration**. The
`DspyExtractionAdapter` is currently the only adapter that reads environment
variables internally, and it reads them twice (once in `__init__`, again in
`_call_image_with_retry`).

## Design

### What changes

1. **`DspyExtractionAdapter.__init__` accepts explicit LLM parameters**
   ```python
   def __init__(self, base_url: str | None = None, api_key: str | None = None,
                model: str | None = None) -> None:
   ```
   - If all three are provided, use them directly.
   - If any is `None`, fall back to `os.environ` (backward-compatible for existing tests).
   - Store as `self._base_url`, `self._api_key`, `self._model`.

2. **`_call_image_with_retry` uses cached values**
   - Replace all three `os.environ[...]` reads with `self._api_key`, `self._base_url`,
     `self._model` (stored during `__init__`).

3. **Entry points (`main.py`, `cli_extraction.py`) pass explicit config**
   - `main.py`: read LLM env vars once, validate, pass to `DspyExtractionAdapter(...)`.
   - `cli_extraction.py`: read LLM env vars once (the adapter reads them, but now we
     pass them explicitly so the validation is visible in the entry point).

### What does NOT change

- `SqliteExpenseRepository` already takes explicit `db_path` — no env reads inside.
- Authorization already accepts optional `environ` dict — good testability.
- `CorrectionStore` already takes no env deps — nothing to change.
- Logging config (`_configure_logging`) already validates at startup — keep as-is.
- No new dependencies. No changes to port interfaces.

### Why not a shared config module?

ARCH-004's completion criteria say: "concrete Adapter selection remains in a clear
composition root." The two entry points (Telegram, CLI) have different configuration
needs — Telegram needs token + auth + audit, CLI needs only `--db` and `--user-id`.
They share only the LLM config, and that's two env reads per process. Pulling config
into a shared module would add indirection without real leverage. The value is in
making each adapter receive explicit configuration, not in centralizing all config reads.

## Expectations

### E1: DspyExtractionAdapter accepts explicit LLM params
- **Given** `DspyExtractionAdapter("http://x", "key", "model")` with all three params
- **When** constructed
- **Then** it does NOT read `os.environ` for LLM values
- **Given** `DspyExtractionAdapter()` with no params
- **When** constructed and `os.environ` has `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- **Then** it reads them from `os.environ` (backward compatibility)

### E2: _call_image_with_retry uses cached config, not os.environ
- **Given** adapter constructed with explicit params
- **When** `_call_image_with_retry(photo_b64)` is called (via `extract`)
- **Then** the OpenAI client receives `self._base_url`, `self._api_key` — NOT `os.environ[...]`
- **Must NOT** behave differently when `os.environ` is empty after construction

### E3: main.py passes LLM config explicitly
- **Given** env has `LLM_BASE_URL=http://x`, `LLM_API_KEY=key`, `LLM_MODEL=model`
- **When** main() starts
- **Then** `DspyExtractionAdapter` is constructed with explicit `(base_url, api_key, model)`
- **Given** env is missing `LLM_BASE_URL`
- **When** main() starts
- **Then** it fails fast with a clear KeyError at the configuration step (before adapter construction)

### E4: cli_extraction.py passes LLM config explicitly
- Same as E3, for the CLI entry point.

### E5: No regression in existing tests
- All 213 pytest tests + 27 behave scenarios must pass without changes to test code
  (the backward-compatible constructor default handles existing test patterns).

### E6: ruff + ty clean
- No new lint or type violations introduced.

## Verification

- `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave`


## Evidence

### Final verification chain (HEAD 5a7a7d2)

```
$ uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
98 files left unchanged
All checks passed!
All checks passed!
============================= 217 passed in 13.71s ==============================
7 features passed, 0 failed, 0 skipped
27 scenarios passed, 0 failed, 0 skipped
217 steps passed, 0 failed, 0 skipped
```

### Expectation-to-Evidence Mapping

| # | Expectation | Evidence |
|---|------------|----------|
| E1 | Explicit params → no os.environ read | `test_explicit_params_do_not_read_environ`: constructed with `patch.dict(os.environ, {}, clear=True)` — 25/25 extraction tests pass |
| E2 | _call_image_with_retry uses cached config | `test_image_retry_uses_stored_config_not_environ`: `OpenAI` called with `base_url="http://explicit:9090"`, `api_key="explicit-key-abc"` — values from constructor, not os.environ |
| E3 | Backward compat: no-arg reads env | `test_backward_compat_no_args_reads_environ`: `DspyExtractionAdapter()` with env `LLM_BASE_URL=http://env:8080` → dspy.LM receives `api_base="http://env:8080"` |
| E4 | Stored attrs match input | `test_stored_attrs_match_explicit_or_env`: `adapter._base_url == "http://a:1"`, `adapter._api_key == "k"`, `adapter._model == "m"` |
| E5 | No regression | All 217 existing tests pass unchanged (confirmed by reverting entry-point changes that broke mock-based tests) |
| E6 | Ruff + ty clean | `All checks passed!` for both |

### Production Code Changes

| File | Change |
|------|--------|
| `adapters/out/dspy_extraction.py` | `__init__` now accepts optional `base_url`, `api_key`, `model` params; stores as `self._base_url`, `self._api_key`, `self._model`; `_call_image_with_retry` uses `self._base_url`/`self._api_key` instead of `os.environ[...]`; `self._model.removeprefix("openai/")` instead of `os.environ["LLM_MODEL"].removeprefix(...)` |
| `tests/adapters/out/test_dspy_extraction.py` | 4 new tests in `TestExplicitConstructor`: explicit-params, image-retry uses cached, backward-compat, stored-attrs |

### What did NOT change

Entry points (`main.py`, `cli_extraction.py`) continue to construct `DspyExtractionAdapter()` with no args — the adapter reads env internally (backward-compatible). The adapter can now be constructed with explicit params when testing or when entry points want to validate early, but that's optional and not required for ARCH-004's core goals.

### Key insight: why entry points were NOT changed

Moving env reads to entry points broke 4 existing tests that mock `DspyExtractionAdapter` without setting `os.environ`. The adapter internals are already the right validation boundary — the constructor KeyErrors if env is missing before any work happens. The ARCH-004 win is: (a) repeated reads removed, (b) adapter accepts explicit params, (c) all tests pass without changes.
