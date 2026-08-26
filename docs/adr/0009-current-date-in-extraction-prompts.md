# ADR 0009: Current Date in Extraction Prompts

**Date:** 2026-08-26
**Status:** Accepted

## Context

Free-text expense messages often omit an explicit date ("10 euros for a taxi").
The extraction LLM had no concept of "now", so it could not resolve the implied
date. The same gap applies to the correction flow: a user replying
"actually it was last Monday" needs the LLM to know what today is to resolve
the relative reference (issue #9, PR #12).

Two questions needed deciding:

1. Where does `current_date` live in the architecture — adapter-only parameter,
   or part of the `ExtractionPort` contract?
2. What happens when no caller supplies it?

## Decision

1. **The port owns the parameter.** `ExtractionPort.extract()` and
   `ExtractionPort.refine()` both accept an optional
   `current_date: date | None = None`. All implementations and fakes share the
   contract; the application layer may pass an explicit date at any time
   without further interface changes.

2. **Server-local fallback is acceptable.** When `current_date` is omitted,
   implementations default to `date.today()` — the timezone of the machine
   running the bot. Callers that need user-timezone accuracy pass an explicit
   date; none do today.

3. **Receipt/image extraction ignores `current_date`.** Receipt photos carry
   their own printed date; the vision path stays untouched.

## Consequences

- The prompt for free-text extraction and refinement prepends
  `Current date: <iso>` plus a fallback instruction so the LLM can infer or
  resolve dates.
- Expenses recorded near midnight by users in timezones ahead of/behind the
  server may be dated off by one day until callers pass an explicit date.
  This is accepted for a single-user deployment co-located with its operator.
- A wall-clock read lives inside the outbound adapter default; tests that need
  determinism pass `current_date` explicitly instead of patching time.
