# Expectations: Current Date in Extraction Prompts

Feature: free-text messages without explicit dates ("10 euros for a taxi")
and correction replies with relative dates ("actually last Monday") must
resolve against a known "today" (issue #9, PR #12, ADR 0009).

## Happy path

1. `ExtractionPort.extract()` accepts optional `current_date: date | None`.
2. `ExtractionPort.refine()` accepts optional `current_date: date | None`.
3. Free-text extraction prompt starts with `Current date: <ISO date>` followed
   by an instruction to assume that date when none is mentioned.
4. Refine prompt carries the same context block before the original/correction
   payload.
5. When `current_date` is omitted, both paths use server-local `date.today()`.

## Edge cases

6. Passing `current_date` explicitly never changes the extracted amount,
   currency, merchant, or category parsing — only date resolution context.
7. Receipt (`ReceiptPagesSourceView`) extraction ignores `current_date`
   entirely: the vision prompt must not contain the supplied date.

## Must NOT happen

8. The image/vision prompt must never receive the "Current date:" context.
9. Callers are never required to pass `current_date` — omission is valid.
10. The port signature change must not break protocol conformance of
    existing adapters/fakes that accept the new optional parameter.
