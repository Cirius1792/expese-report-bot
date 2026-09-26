Feature: Reply keyboard bottom action bar
  As a user
  I want persistent buttons below the input field
  So that I can add, list, report, and remove expenses without typing commands

  Background:
    Given the bot is running
    And the extraction service is working
    And the database is empty

  Scenario: /start attaches the bottom action bar
    When I send the command "/start"
    Then the bot should reply with a confirmation containing "buttons below the input field"
    And the bot shows the reply keyboard

  Scenario: A saved expense confirmation is followed by the action bar
    Given I have no pending corrections
    And the LLM extracts amount "3.50", currency "EUR", merchant "Central Cafe", date "2026-07-12"
    When I send the message "coffee 3.50 eur at Central Cafe 2026-07-12"
    Then the bot should reply with a confirmation containing "Saved"
    And the bot shows the reply keyboard

  Scenario: Tapping "Add" asks for a receipt
    When I press the keyboard button "Add"
    Then the bot should reply with a confirmation containing "receipt"
    And the database should still be empty

  Scenario: Tapping "List" shows the list view
    When I press the keyboard button "List"
    Then the bot should reply with a confirmation containing "no recorded expenses"
    And the database should still be empty

  Scenario: Tapping "Report" runs the monthly report flow
    Given I have recorded the following expenses this month:
      | amount | currency | merchant | date       |
      | 10.00  | EUR      | Shop A   | 2026-07-01 |
    When I press the keyboard button "Report"
    Then the bot should send a CSV file named "expenses-2026-07.csv"

  Scenario: Tapping "Help" shows the welcome message and the action bar
    When I press the keyboard button "Help"
    Then the bot should reply with a confirmation containing "Welcome!"
    And the bot shows the reply keyboard

  Scenario: Tapping "Remove" explains how to delete
    When I press the keyboard button "Remove"
    Then the bot should reply with a confirmation containing "delete"
    And the database should still be empty
