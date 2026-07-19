# Expectations: Vertical Slice 1 — CLI extraction + storage

## Happy path — text extraction

- **Given** env vars `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` are set to a working OpenAI-compatible endpoint
- **When** `DspyExtractionAdapter.extract()` is called with a text string like `"lunch 15 eur"` and `source_type="text"`
- **Then** it initializes dSPy LM with the env vars, calls dSPy ChainOfThought with the ExpenseSignature, and returns an `ExtractionResult` with parsed fields

## Happy path — image extraction

- **Given** image bytes from a receipt photo
- **When** `DspyExtractionAdapter.extract()` is called with `source=bytes` and `source_type="image"`
- **Then** the image bytes are base64-encoded into a `data:image/jpeg;base64,...` URL string before being passed to the dSPy predictor

## Happy path — save and retrieve

- **Given** a `SqliteExpenseRepository` with an in-memory or file-based SQLite DB
- **When** an `Expense` with `id=None` is saved
- **Then** a UUID4 string is generated as the id, and the same expense is returned with the id populated

## Edge cases — field validation

- **Currency**: If the LLM returns a value that is not exactly 3 uppercase letters (`^[A-Z]{3}$`), the currency is set to `None`. Lowercase "eur" → `None`, "INVALID" → `None`, "EU" → `None`, "EURO" → `None`.
- **Date**: If the LLM returns a value that is not valid `YYYY-MM-DD`, the date is set to `None`. Empty string → `None`, "not-a-date" → `None`.
- **Amount**: If the LLM returns a value that cannot be parsed as `Decimal`, the amount is set to `None`. Empty string → `None`, "not-a-number" → `None`.
- **Merchant**: Empty string → `None`
- **Category**: Empty string → `None`

## Edge cases — retry logic

- **On transient failure** (network error, rate limit): retries up to 2 more times with exponential backoff (1s, 2s)
- **On persistent failure**: all 3 attempts fail, the last exception is re-raised

## Edge cases — repository

- **get_by_id unknown**: returns `None`
- **get_by_user_and_month empty**: returns `[]`
- **Other users' expenses**: filtered out by `user_id`
- **Other months**: filtered out by month prefix match
- **Ordering**: `created_at DESC`
- **Decimal precision**: amounts survive round-trip without precision loss
- **Nullable fields**: `category=None` and `receipt_photo_id=None` survive round-trip

## Behaviors that must NOT happen

- Domain layer must NOT import dSPy, sqlite3, or any adapter/framework code
- Adapters must NOT use `Any` or untyped `dict` as parameter/return types
- The `in/` directory must NOT be used as a module name (Python 3.10 parser bug with `from X.in.Y import Z`)
- No secrets or tokens in source code
- No real LLM calls during tests — all external boundaries must be mocked
