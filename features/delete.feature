Feature: Delete Saved Expenses
  As a user
  I want to delete saved expenses by id or from the creation message
  So that I can remove mistakes from my records

  Background:
    Given the bot is running
    And the database is empty

  @story-17
  Scenario: /delete removes a saved expense and confirms what was deleted
    Given the following expenses exist:
      | id | amount | currency | merchant    | date       | category  |
      | 1  | 42.50  | EUR      | Supermarket | 2026-07-10 | groceries |
      | 2  | 12.50  | EUR      | Coffee Shop | 2026-07-15 | food      |
    When I send the command "/delete 2"
    Then the delete reply should be "🗑️ Deleted expense #2: Coffee Shop — 12.50 EUR — 2026-07-15"
    And expense #2 should no longer be recorded

  @story-17
  Scenario: /delete reports not found for an expense outside my records
    Given the following expenses exist:
      | id | amount | currency | merchant       | date       | user_id |
      | 1  | 50.00  | EUR      | User 123 Shop  | 2026-07-10 | 123     |
      | 2  | 25.00  | EUR      | User 456 Shop  | 2026-07-11 | 456     |
    When user 123 sends the delete command "/delete 2"
    Then the delete reply should be "Expense #2 was not found."
    And expense #2 should still be recorded for user 456

  @story-17
  Scenario: Invalid /delete commands show the usage message
    When I send invalid delete commands:
      | command          |
      | /delete          |
      | /delete abc      |
      | /delete 42 extra |
    Then each delete command should reply with "Usage: /delete <expense_id>"

  @story-18
  Scenario: Delete button strikes through the original saved-expense message
    Given a saved confirmation for expense #1 exists:
      | id | amount | currency | merchant     | date       | category |
      | 1  | 3.50   | EUR      | Central Cafe | 2026-07-12 | food     |
    When I tap the delete button for expense #1
    Then the edited confirmation still contains "Central Cafe"
    And the edited confirmation shows struck-through expense details
    And the edited confirmation includes "🗑️ Deleted."
    And the delete button is removed from the edited confirmation
    And expense #1 should no longer be recorded
