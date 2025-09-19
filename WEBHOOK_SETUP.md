# Coinbase Commerce Webhook Setup Guide

This guide will help you set up the Coinbase Commerce webhook to enable real cryptocurrency payments in your Trustlink escrow system.

## Prerequisites

1. **Coinbase Commerce Account**: Sign up at https://commerce.coinbase.com/
2. **API Keys**: Get your API key and webhook secret from Coinbase Commerce dashboard
3. **ngrok**: Tool to expose your local server publicly

## Step 1: Install ngrok

### Option A: Download from website
1. Go to https://ngrok.com/download
2. Download the appropriate version for your system
3. Extract and move to `/usr/local/bin/` or add to PATH

### Option B: Using package manager (Linux)
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install snapd
sudo snap install ngrok

# Or using wget
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin
```

## Step 2: Configure Environment Variables

Add your Coinbase Commerce credentials to your `.env` file:

```bash
# Coinbase Commerce Configuration
COINBASE_COMMERCE_API_KEY=your-api-key-here
COINBASE_COMMERCE_WEBHOOK_SECRET=your-webhook-secret-here
```

## Step 3: Start Your Django Server

Open a new terminal and start the Django development server:

```bash
cd /home/pirate/Documents/Projects/Trustlink/Trustlink
source venv/bin/activate
python manage.py start_server --port 8000 --host 0.0.0.0
```

The server will start and show:
```
Starting Django server on 0.0.0.0:8000...
Webhook endpoint will be available at: http://0.0.0.0:8000/escrow/webhooks/coinbase/
```

## Step 4: Expose Server with ngrok

Open another terminal and run:

```bash
ngrok http 8000
```

You'll see output like:
```
ngrok by @inconshreveable

Session Status                online
Account                       your-account
Version                       3.x.x
Region                        United States (us)
Latency                       -
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://abc123.ngrok.io -> http://localhost:8000
```

**Important**: Copy the HTTPS forwarding URL (e.g., `https://abc123.ngrok.io`)

## Step 5: Configure Coinbase Commerce Webhook

1. **Login to Coinbase Commerce**: Go to https://commerce.coinbase.com/
2. **Navigate to Settings**: Click on "Settings" in the left sidebar
3. **Go to Webhook Settings**: Click on "Webhook subscriptions"
4. **Add New Webhook**:
   - **Endpoint URL**: `https://your-ngrok-url.ngrok.io/escrow/webhooks/coinbase/`
   - **Events**: Select all payment-related events:
     - `charge:created`
     - `charge:confirmed` 
     - `charge:failed`
     - `charge:delayed`
     - `charge:pending`
     - `charge:resolved`

5. **Save the Webhook**: Click "Create" or "Save"

## Step 6: Test the Webhook

### Test webhook endpoint manually:
```bash
curl -X POST https://your-ngrok-url.ngrok.io/escrow/webhooks/coinbase/ \
  -H "Content-Type: application/json" \
  -H "X-CC-Webhook-Signature: test" \
  -d '{"test": "data"}'
```

### Check Django logs:
Monitor your Django server terminal for webhook requests.

### Check ngrok web interface:
Open http://127.0.0.1:4040 in your browser to see incoming requests.

## Step 7: Update Environment Variables (Optional)

If you want to set a fixed webhook URL, add to your `.env`:

```bash
TELEGRAM_WEBHOOK_URL=https://your-ngrok-url.ngrok.io
```

## Troubleshooting

### Common Issues:

1. **"Invalid signature" errors**:
   - Verify your `COINBASE_COMMERCE_WEBHOOK_SECRET` is correct
   - Check that the secret matches what's in your Coinbase Commerce dashboard

2. **Connection refused**:
   - Ensure Django server is running on the correct port
   - Check that ngrok is forwarding to the right port

3. **404 errors**:
   - Verify the webhook URL path: `/escrow/webhooks/coinbase/`
   - Check Django URL configuration

4. **ngrok session expired**:
   - Free ngrok sessions expire after 8 hours
   - Restart ngrok and update the webhook URL in Coinbase Commerce

### Logs to Check:

1. **Django server logs**: Check the terminal running `start_server`
2. **ngrok logs**: Check the terminal running `ngrok http 8000`
3. **ngrok web interface**: http://127.0.0.1:4040
4. **Django admin**: Check PaymentWebhook records at `/admin/`

## Production Deployment

For production, replace ngrok with:
- **Reverse proxy** (nginx + SSL certificate)
- **Cloud hosting** (Heroku, DigitalOcean, AWS, etc.)
- **Domain name** with HTTPS

## Security Notes

- Always use HTTPS for webhook endpoints
- Verify webhook signatures to prevent spoofing
- Keep your API keys and webhook secrets secure
- Monitor webhook logs for suspicious activity

## Next Steps

Once the webhook is working:
1. Test end-to-end payment flow through your Telegram bot
2. Monitor payment confirmations in Django admin
3. Set up notification system for payment events
4. Configure production hosting for your application
