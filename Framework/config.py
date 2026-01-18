import os

# Telegram Bot Token from BotFather
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Solana Configuration
DEPOSIT_ADDRESS = os.environ.get('DEPOSIT_ADDRESS')  # The address users will send SOL to
REQUIRED_PAYMENT = float(os.environ.get('REQUIRED_PAYMENT', '0.5'))  # Amount in SOL required for premium

# Commission percentage
COMMISSION_PERCENTAGE = float(os.environ.get('COMMISSION_PERCENTAGE', '10.0'))

# Helius Configuration
HELIUS_API_KEY = os.environ.get('HELIUS_API_KEY')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')

# Database Configuration - SQLite
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'translucent_bot.db')  # SQLite database file

# Server Configuration
WEBHOOK_HOST = os.environ.get('WEBHOOK_HOST')

WEBHOOK_PATH = os.environ.get('WEBHOOK_PATH', '/telegram_webhook')  # This is for Telegram updates
PAYMENT_WEBHOOK_PATH = os.environ.get('PAYMENT_WEBHOOK_PATH', '/payment_webhook')  # This is for Helius payment updates
PORT = int(os.environ.get('PORT', '8000'))  # Port for Telegram webhook
PAYMENT_PORT = int(os.environ.get('PAYMENT_PORT', '5001'))  # Port for payment webhook

# Admin user IDs (comma-separated list of Telegram IDs)
ADMIN_IDS = [int(id) for id in os.environ.get('ADMIN_IDS', '').split(',') if id.strip()]

# Authentication Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-super-secret-key-change-this-in-production')
AUTH_SERVER_URL = WEBHOOK_HOST  # Use the same ngrok URL
WEBSITE_URL = WEBHOOK_HOST  # Use the same ngrok URL
AUTH_TOKEN_EXPIRY = int(os.environ.get('AUTH_TOKEN_EXPIRY', '15'))  # minutes 