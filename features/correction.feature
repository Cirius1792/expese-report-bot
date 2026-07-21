Feature: Correction Loop
  As a user
  I want to correct partial or wrong extractions
  So that my final stored expenses are accurate

  Background:
    Given the bot is running
    And the extraction service is working
    And the database is empty

  @story-6
  Scenario: Partial extraction from photo prompts for missing fields
    Given I have a valid receipt photo
    When I send a receipt photo
    And the LLM extracts only the amount "15.00" without currency, merchant, or date
    Then the bot should not save any expense
    And the bot should ask for missing fields
    And the missing fields should include "currency", "merchant", and "date"
    And the pending correction should be stored for my user

  @story-7 @story-8
  Scenario: User corrects missing fields via text
    Given I have a pending correction with amount "15.00" but missing currency, merchant, and date
    When I reply with the correction text "it was EUR 15 at Ristorante Roma on 2026-07-18"
    And the LLM refines the extraction to be complete with merchant "Ristorante Roma" and date "2026-07-18"
    Then the bot should save the expense with all fields
    And the bot should reply with a confirmation containing "Updated and saved"
    And the bot should reply with a confirmation containing "Expense #1"
    And the bot shows exactly these buttons: "🗑️ Delete"
    And the pending correction should be cleared

  @story-7 @story-8
  Scenario: User corrects wrong fields from the original extraction
    Given I have a pending correction with amount "20.00", currency "USD", but wrong merchant "Unknown"
    When I reply with the correction text "the merchant was actually Best Western Hotel"
    And the LLM refines the extraction with merchant "Best Western Hotel"
    Then the bot should save the expense with merchant "Best Western Hotel"
    And the saved expense should have amount "20.00" and currency "USD"
    And the bot should reply with a confirmation containing "Expense #1"
    And the bot shows exactly these buttons: "🗑️ Delete"

  Scenario: Correction still incomplete — ask again
    Given I have a pending correction with only amount "10.00"
    When I reply with the correction text "it was at a cafe"
    And the LLM refines but still cannot determine currency or date
    Then the bot should not save any expense
    And the bot should tell me which fields are still missing
    And the correction attempt count should increase to 2

  Scenario: Max correction attempts exhausted
    Given I have a pending correction that has already been attempted 3 times
    When I reply with another correction text
    Then the bot should not call the LLM again
    And the bot should tell me the extraction could not be completed
    And the pending correction should be removed
