# Expense Report Bot

A Telegram bot that receives receipt photos, extracts structured expense data via an external LLM, and stores expenses for later reporting.

## Language

**Receipt**:
A photo of a merchant-issued document (paper or digital) sent to the bot by the user.
_Avoid_: Expense, bill, ticket

**Expense**:
A structured record of money spent, extracted from a Receipt. Contains amount, currency, merchant, date, and optionally category.
_Avoid_: Receipt, transaction, charge

**Expense Report**:
A CSV export of all Expenses within the current calendar month.

**Category**:
A label classifying an Expense (e.g., hotel, food, flight, fuel, train, car).
The LLM is prompted to prefer known categories but may propose new ones as free-text when none match.

**Currency**:
The three-letter ISO 4217 currency code (e.g., EUR, USD, GBP) as extracted from the Receipt.
No conversion to a base currency — Expenses retain their original currency in the report.

**Extraction**:
The LLM's structured output (amount, currency, merchant, date, category) parsed from either a Receipt photo (vision-based) or a free-text message (when no receipt is available, e.g., cash expenses).
An Extraction may be partial — missing mandatory fields triggers Correction.

**Correction**:
A user's text reply filling gaps or overriding fields in a partial Extraction.
The Correction is fed back to the LLM alongside the original Extraction to produce a final, complete Extraction.

**User**:
A Telegram user identified by their Telegram user_id. Each User's Expenses are isolated — a User can only see and manage their own Expenses.

## Relationships

- A **Receipt** produces exactly one **Expense**
- An **Expense** is derived from exactly one **Receipt**
- An **Expense Report** aggregates zero or more **Expenses** for the current month

## Example dialogue

> **Dev:** "When the LLM fails to extract the merchant from a Receipt, what happens?"
> **Domain expert:** "The bot shows the user what was extracted and asks to fill the missing fields. This is a Correction."
> **Dev:** "And if the user sends just text like 'lunch 15 eur'?"
> **Domain expert:** "That's still an Extraction — we treat it as a cash Expense with no Receipt photo. The LLM extracts from the text directly."

## Flagged ambiguities

- "expense" was used to mean both the Receipt photo and the stored record — resolved: Receipt is the photo, Expense is the stored data.
