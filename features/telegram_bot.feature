Feature: Telegram Bot Shell
  As a user
  I want to interact with the bot by sending photos and text
  So that my expenses are automatically extracted and displayed

  Background:
    Given the bot is running
    And the extraction service is working
    And the database is empty

  @story-3
  Scenario: Send receipt photo with complete extraction
    Given I have a valid receipt photo
    When I send the photo to the bot
    And the LLM extracts amount "42.50", currency "EUR", merchant "Supermarket", date "2026-07-15", and category "groceries"
    Then the bot should reply with a confirmation containing "42.50"
    And the bot should reply with a confirmation containing "Supermarket"
    And the bot should reply with a confirmation containing "Expense #1"
    And the bot should reply with a confirmation containing "Saved"
    And the bot shows exactly these buttons: "🗑️ Delete"
    And the expense should be persisted with amount 42.50 EUR

  @story-4
  Scenario: Send free-text expense message
    Given I have no pending corrections
    And the LLM extracts amount "3.50", currency "EUR", merchant "Central Cafe", date "2026-07-12"
    When I send the message "coffee 3.50 eur at Central Cafe 2026-07-12"
    Then the bot should reply with a confirmation containing "3.50"
    And the bot should reply with a confirmation containing "Expense #1"
    And the bot should reply with a confirmation containing "Saved"
    And the bot shows exactly these buttons: "🗑️ Delete"
    And the expense should be persisted with merchant "Central Cafe"

  Scenario: Receive /start command
    When I send the command "/start"
    Then the bot should reply with a welcome message
    And the welcome message should mention "expense"
