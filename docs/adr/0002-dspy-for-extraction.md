# ADR 0002: dSPy for Extraction Pipeline

**Date:** 2026-07-19
**Status:** Accepted

## Context

The bot's core function is extracting structured Expense data from receipt photos and free-text messages via an external LLM. We plan to build a fine-tuning/optimization pipeline later using a dataset of known receipts to improve extraction accuracy.

## Decision

Use dSPy for the extraction pipeline at runtime from day one — not just for offline optimization later but as the active inference framework on every extraction call.

This avoids a full refactor later: if we start with plain prompt engineering, we must port to dSPy Signatures and Modules when the optimization pipeline arrives. Starting with dSPy means the optimization phase is just running a dSPy compiler (MIPROv2, BootstrapFewShot, etc.) over existing modules.

## Considered Options

| Option | Upfront cost | Future cost |
|--------|-------------|-------------|
| dSPy at runtime (chosen) | Higher — dSPy module overhead, opaque prompt construction | Zero — optimizers run over existing modules |
| Plain prompt, dSPy later | Lower — direct LLM calls, simple to debug | High — full extraction pipeline rewrite into dSPy Signatures |
| Plain prompt forever | Lowest | None, but no optimization path |

## Consequences

- Every extraction call goes through dSPy module machinery (Signature → ChainOfThought → LLM call)
- Debugging extraction quality is harder due to dSPy's internal prompt construction
- The optimization pipeline reuses the same modules, no code changes needed
- Dependencies: `dspy-ai` must be in pyproject.toml
