Feature: Monthly Expense Report
  As a user
  I want to export my expenses as CSV for the current month
  So that I can use the data for accounting or reimbursement

  Background:
    Given the bot is running
    And the database is empty

  @story-9
  Scenario: Report returns CSV for current month with expenses
    Given I have recorded the following expenses this month:
      | amount | currency | merchant    | date       | category   |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | groceries  |
      | 15.00  | EUR      | Cafe Central | 2026-07-12 | food       |
      | 120.00 | USD      | Hotel Luxe   | 2026-07-14 | hotel      |
    When I send the command "/report"
    Then the bot should send a CSV file named "expenses-2026-07.csv"
    And the CSV should contain 3 expense rows
    And the CSV should contain "Supermarket"
    And the bot should reply with "Generated report with 3 expenses"

  @story-9
  Scenario: Report with no expenses returns informative message
    Given I have no expenses recorded this month
    When I send the command "/report"
    Then the bot should reply with "No expenses recorded for 2026-07"
    And the bot should not send any file

  @story-10
  Scenario: Report isolates expenses by user
    Given user 123 has recorded an expense of 50.00 EUR at "User 123 Shop"
    And user 456 has recorded an expense of 30.00 EUR at "User 456 Shop"
    When user 123 requests /report
    Then the CSV should contain "User 123 Shop"
    And the CSV should not contain "User 456 Shop"
