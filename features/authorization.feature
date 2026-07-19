Feature: Telegram user authorization
  As the bot owner
  I want only whitelisted Telegram users to interact with the bot
  So that unauthorized users cannot use the expense-report bot

  Background:
    Given the bot is running
    And the extraction service is working
    And the database is empty

  @story-11
  Scenario: Authorized user can send a free-text expense message
    Given the bot authorization whitelist contains my Telegram user ID
    When I send a free-text expense message "coffee 3.50 eur at Central Cafe 2026-07-12" through the authorization gate
    Then the bot should send a reply

  @story-11
  Scenario: Unauthorized user is silently ignored and logged
    Given the bot authorization whitelist does not contain my Telegram user ID
    When I send a free-text expense message "coffee 3.50 eur at Central Cafe 2026-07-12" through the authorization gate
    Then the bot should not send any reply
    And the unauthorized attempts log should contain my Telegram user ID
    And the unauthorized attempts log should contain an ISO-8601 UTC timestamp
