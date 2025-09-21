# Trustlink Project Documentation

**Version: 1.0**
**Last Updated: September 20, 2025**

This document provides a comprehensive overview of the Trustlink platform, including its features, workflow, and technical details.

## 1. Project Overview

Trustlink is a secure platform for buying and selling Telegram groups, built around an automated escrow system to ensure trust and safety for all parties. The system is composed of a Django backend that powers a marketplace API and a user-friendly Telegram bot that handles all user interactions, from registration and listing to the final purchase.

## 2. Features Implemented

### Core Backend & API

-   **Full Escrow System**: Manages the entire lifecycle of a transaction, from initiation to completion or dispute.
-   **Database Models**: Robust Django models for `TelegramUser`, `GroupListing`, `EscrowTransaction`, and various logging tables.
-   **Marketplace API**: A public REST API (`/api/groups/listings/`) allows users to browse and view active group listings, with support for filtering, searching, and ordering.

### Telegram Bot

-   **User-Friendly Navigation**:
    -   **Persistent Keyboard**: A main menu with large, tappable buttons (`Browse Listings`, `List a Group`, `My Profile`, `Help`) is always visible for easy access to core features.
    -   **Contextual Inline Menus**: After certain commands, the bot provides contextual inline buttons. For example, the `My Profile` section has direct links to `My Listings` and `Transaction History`.
-   **Secure Group Listing Process**: A guided, 5-step flow for sellers:
    1.  **Ownership Verification**: The bot automatically verifies that the user is the creator of the Telegram group and that the bot has been added as an administrator.
    2.  **Title & Description**: The user provides a title and description for the listing.
    3.  **Price**: The user sets the price in USD.
    4.  **Category**: The user selects a category for the group.
    5.  **Confirmation**: The user reviews all details before the listing is created and becomes active in the marketplace.
-   **Marketplace Functionality**:
    -   Users can browse all listings with the `Browse Listings` button or the `/browse` command.
    -   Users can view detailed information about a specific group with the `/view <id>` command.
-   **User Profile**: A dedicated profile section where users can view their trading statistics and navigate to their listings and transaction history.

## 3. System Workflow

### New User Registration

1.  A new user starts the bot and is prompted to register.
2.  The user provides their full name and confirms the details.
3.  The bot creates a verified user account, linking their Telegram ID to a new user in the database.

### Seller: Listing a Group

1.  A registered user selects `📝 List a Group`.
2.  The bot asks for the group's username (e.g., `@mygroup`).
3.  The bot verifies ownership by checking if the user is the group's creator.
4.  If verified, the user proceeds through the remaining steps: title, description, price, and category.
5.  After a final confirmation, the `GroupListing` is created in the database and becomes publicly available in the marketplace.

### Buyer: Browsing and Purchasing

1.  A user selects `🏪 Browse Listings`.
2.  The bot displays a list of active group listings from the marketplace API.
3.  The user can use `/view <id>` to see more details about a specific group.
4.  From the detail view, the user can click a "Buy" button to initiate the escrow transaction process (note: the transaction flow itself is the next major feature to be fully implemented).

## 4. Technical Stack

-   **Backend**: Django, Django REST Framework
-   **Database**: SQLite (default, can be configured for PostgreSQL)
-   **Telegram Bot**: `python-telegram-bot`
-   **HTTP Client**: `httpx` for asynchronous API requests from the bot

## 5. Remaining Tasks & Future Work

While the core functionality for user registration and group listing is complete, the following key areas are planned for future development:

-   **Complete the Purchase & Escrow Flow**: Implement the full transaction lifecycle, including payment processing, automated verification of group ownership transfer, and fund release.
-   **Dispute Resolution System**: Build out the functionality for users to open and manage disputes, with an admin interface for arbitration.
-   **Notifications**: Implement a notification system to alert users about key events (e.g., new purchase requests, payment confirmations, dispute updates).
-   **Advanced Group Monitoring**: Enhance the system to periodically check for changes in group ownership or admin status for ongoing security.
-   **User Balances & Payouts**: Implement a system for sellers to manage their earnings and request payouts.
ee