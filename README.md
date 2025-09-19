# Trustlink - Secure Telegram Group Escrow Bot

Trustlink is a powerful, secure, and reliable Telegram bot designed to facilitate the buying and selling of Telegram groups through a trusted escrow system. It leverages the security of cryptocurrency payments and a robust dispute resolution process to ensure safe transactions for both buyers and sellers.

  <!-- Replace with your own banner -->

## 🌟 Key Features

- **Secure Escrow System**: Funds are held securely until both parties confirm the transaction is complete.
- **Cryptocurrency Payments**: Supports major cryptocurrencies like USDT, ETH, and BTC through Coinbase Commerce.
- **Automated Notifications**: Real-time updates on transaction status, payments, and disputes.
- **User-Friendly Interface**: Easy-to-use commands for listing, buying, and managing transactions directly within Telegram.
- **Dispute Resolution**: A built-in system to handle and resolve conflicts with admin oversight.
- **Admin Dashboard**: A comprehensive Django admin panel for managing users, transactions, and disputes.

## 🚀 Getting Started

Follow these steps to set up and run the Trustlink bot in your local environment.

### Prerequisites

- Python 3.10+
- Django 4.x
- A Telegram Bot Token (get one from [@BotFather](https://t.me/BotFather))
- A Coinbase Commerce account and API keys
- `ngrok` for local webhook testing

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/trustlink.git
cd trustlink
```

### 2. Set Up the Environment

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Now, edit the `.env` file with your favorite editor (e.g., `nano .env`) and add your keys:

```ini
# Django Settings
SECRET_KEY='your-django-secret-key'
DEBUG=True

# Database (default is SQLite)
# DATABASE_URL=postgres://user:password@host:port/dbname

# Telegram Bot
TELEGRAM_BOT_TOKEN='your-telegram-bot-token'

# Coinbase Commerce
COINBASE_COMMERCE_API_KEY='your-coinbase-api-key'
COINBASE_COMMERCE_WEBHOOK_SECRET='your-coinbase-webhook-secret'
```

### 4. Set Up the Database

Run the database migrations to create the necessary tables:

```bash
python manage.py migrate
```

Create a superuser to access the Django admin dashboard:

```bash
python manage.py createsuperuser
```

### 5. Run the Application

You'll need to run two services in separate terminals:

**Terminal 1: Start the Telegram Bot**

```bash
source venv/bin/activate
python manage.py run_bot
```

**Terminal 2: Start the Django Server (for webhooks)**

```bash
source venv/bin/activate
python manage.py start_server
```

### 6. Configure the Webhook

For local development, you need to expose your server to the internet using `ngrok`.

**Terminal 3: Start ngrok**

```bash
ngrok http 8000
```

- Copy the HTTPS URL provided by `ngrok` (e.g., `https://random-string.ngrok.io`).
- Go to your Coinbase Commerce dashboard, navigate to **Settings > Webhook subscriptions**, and add a new webhook pointing to `YOUR_NGROK_URL/escrow/webhooks/coinbase/`.

For detailed instructions, see `WEBHOOK_SETUP.md`.

## 🤖 Bot Commands

- `/start` - Welcome message and main menu.
- `/register` - Create your Trustlink account.
- `/profile` - View your profile and transaction history.
- `/list_group` - Create a new listing to sell a group.
- `/buy` - Browse and purchase available group listings.
- `/help` - Get help and a list of all commands.

## 🛠️ Admin Dashboard

Access the admin dashboard at `http://127.0.0.1:8000/admin/`.

Here you can:
- Manage users and their verification status.
- Oversee all escrow transactions.
- View payment details and webhook logs.
- Manage and resolve disputes.

## 🤝 Contributing

Contributions are welcome! If you'd like to improve Trustlink, please follow these steps:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature-name`).
3. Make your changes and commit them (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature/your-feature-name`).
5. Open a pull request.

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

*Disclaimer: This bot is for educational and illustrative purposes. Always exercise caution when dealing with real financial transactions.*
