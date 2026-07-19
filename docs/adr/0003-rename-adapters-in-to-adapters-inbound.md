# ADR 0003: Rename `adapters/in/` to `adapters/inbound/`

**Date:** 2026-07-19
**Status:** Accepted

## Context

The canonical hexagonal architecture convention uses `adapters/in/` for driving adapters (input channels). However, the repo targets Python 3.12+ for runtime but the development CI and local dev environment run Python 3.10 for some checks.

Python 3.10's parser (CPython < 3.11, PEG parser) cannot parse `from X.in.Y import Z` statements because `in` is a keyword in the `from ... import` grammar, and the older parser treats `X.in.Y` as `X` then keyword `in` before the parser continues to `Y import Z`.

Python 3.11+ with the PEG parser handles this correctly.

## Decision

Rename `src/expense_report/adapters/in/` → `src/expense_report/adapters/inbound/`.

This is a purely cosmetic rename that avoids a CPython 3.10 grammar limitation while preserving the hexagonal intent ("inbound" is semantically equivalent to "in" for driving adapters).

## Consequences

- All imports change from `adapters.in.X` to `adapters.inbound.X`
- The convention differs slightly from some hexagonal architecture references
- Any future developer reading the code will understand `inbound` as "incoming/driving adapters"
- No runtime impact — the module structure is entirely a Python package naming concern
