# ADR 0006: Application-Owned Expense Recording Interface

**Date:** 2026-07-21
**Status:** Accepted

## Context

Telegram and CLI are driving Adapters that independently orchestrate Extraction, Expense construction, and persistence. Telegram also owns the Correction lifecycle. This puts application workflow policy in driving Adapters and leaves no framework-independent driving Interface for tests or future Adapters.

ADR 0001 says every Adapter implements a port Protocol. That is accurate for driven Adapters but not for driving Adapters in hexagonal architecture: driving Adapters consume an application Interface.

## Decision

Create an application-owned `ExpenseRecordingPort` consumed by Telegram and CLI and implemented by an application Module. The Interface exposes one mode-aware Expense Recording operation. `ONE_SHOT` preserves CLI behavior without Correction; `CONVERSATIONAL` supports Telegram's existing Correction workflow.

The application Implementation invokes `ExtractionPort` and `ExpenseRepositoryPort` and owns Extraction-to-save orchestration, Expense construction, and Correction lifecycle decisions. Driving Adapters retain transport translation and rendering.

This ADR supersedes only ADR 0001's statement that every Adapter implements a port Protocol. Driven Adapters implement driven Interfaces; driving Adapters consume driving Interfaces.

## Consequences

- Workflow tests use the same driving Interface as production Adapters without PTB or argparse types.
- Telegram and CLI share one orchestration Implementation while preserving distinct interaction modes.
- Correction state remains an in-process Implementation detail; no speculative storage port is added.
- Receipt-photo and Correction paths may migrate incrementally, but ARCH-001 remains unresolved until all required orchestration is behind the new Seam.
