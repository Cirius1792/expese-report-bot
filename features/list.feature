Feature: Monthly Expense List (Interactive)
  As a user
  I want to browse my expenses by month with inline buttons
  So that I can quickly see what I spent in any month

  Background:
    Given the bot is running
    And the database is empty

  @story-11
  Scenario: /list shows current month with total and only months that have expenses
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 12.50  | EUR      | Coffee Shop  | 2026-07-20 | food     |
      | 30.00  | EUR      | Book Store   | 2026-03-05 | shopping |
    When I send the command "/list"
    Then the message shows expenses for July 2026
    And the message shows the total "55.00"
    And the bot shows buttons labeled "2026", "Jul", and "Mar"
    And the bot does not show a button labeled "2025"
    And the message explains that only months with expenses are shown

  @story-12
  Scenario: /list with no expenses shows informative message without buttons
    Given I have no expenses recorded
    When I send the command "/list"
    Then the bot replies with a message that no expenses are recorded
    And the bot does not show any year or month buttons

  @story-13
  Scenario: /list isolates expenses by user
    Given the following expenses exist:
      | amount | currency | merchant       | date       | user_id |
      | 50.00  | EUR      | User 123 Shop  | 2026-07-01 | 123     |
      | 25.00  | EUR      | User 456 Shop  | 2026-07-02 | 456     |
    When user 123 sends the command "/list"
    Then the message shows expenses for user 123
    And the bot shows buttons labeled "2026" and "Jul"

  @story-14
  Scenario: Tapping a month button navigates to that month
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 30.00  | EUR      | Book Store   | 2026-03-05 | shopping |
    Given the list view for the current month is displayed
    When the user selects month "Mar"
    Then the message updates to show expenses for March 2026
    And the message shows the total "30.00"

  @story-15
  Scenario: Tapping a year button switches to that year and shows year total
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 30.00  | EUR      | Book Store   | 2026-03-05 | shopping |
      | 15.00  | EUR      | Old Shop     | 2025-12-01 | shopping |
    Given the list view for the current month is displayed
    When the user selects year "2025"
    Then the message shows the year total "15.00"
    And the bot shows buttons labeled "2026", "2025", and "Dec"

  @story-16
  Scenario: Previous year button appears only when expenses exist in that year
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 15.00  | EUR      | Old Shop     | 2025-12-01 | shopping |
      | 20.00  | EUR      | Last Jan     | 2025-01-15 | food     |
    When I send the command "/list"
    Then the bot shows exactly these buttons: "2026, 2025, Jul, Jan, Dec"
