Feature: CLI Expense Extraction and Storage
  As a developer
  I want to extract structured expense data from receipt images and free text via CLI
  So that I can verify the LLM extraction pipeline end-to-end without Telegram

  Background:
    Given the LLM extraction service is available
    And the expense database is empty

  @story-1
  Scenario: Extract expense from receipt image via CLI
    Given a receipt image file "motorway_toll.jpg" with encoded content
    When I run the CLI command "extract-from-image" with that image
    Then the extracted amount should be "3.80"
    And the extracted currency should be "EUR"
    And the extracted merchant should be "Autostrade per l'Italia"
    And the extracted date should be "2026-07-15"
    And the extraction should be complete
    And the expense should be saved to the database

  @story-2
  Scenario: Extract expense from free-text message via CLI
    Given the user describes an expense as "lunch 15.50 eur at Mario's Pizzeria on 2026-07-10"
    When I run the CLI command "extract-from-text" with that text
    Then the extracted amount should be "15.50"
    And the extracted currency should be "EUR"
    And the extracted merchant should be "Mario's Pizzeria"
    And the extracted date should be "2026-07-10"
    And the extraction should be complete
    And the expense should be saved to the database

  @story-2
  Scenario: Extract expense with optional category from text
    Given the user describes an expense as "taxi 25 usd transport"
    And the LLM will extract amount "25.00", currency "USD", merchant "Taxi", date "2026-07-15", and category "transport"
    When I run the CLI command "extract-from-text" with that text
    Then the extracted amount should be "25.00"
    And the extracted currency should be "USD"
    And the extracted category should be "transport"
    And the expense should be saved to the database

  Scenario: Partial extraction from ambiguous text
    Given the user describes an expense as "something expensive"
    And the LLM will only extract the amount "100.00"
    When I run the CLI command "extract-from-text" with that text
    Then the extraction should not be complete
    And the database should still be empty
