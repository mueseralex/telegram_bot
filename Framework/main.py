import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from config import BOT_TOKEN, WEBHOOK_HOST, WEBHOOK_PATH, PORT
from database import Database
from handlers.start_handler import start_command
from handlers.referral_handler import referral_command
from handlers.admin_handler import admin_stats, lookup_user, whitelist_user

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(f"Hi {user.first_name}! I'm your bot. Use /help to see available commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    await update.message.reply_text(update.message.text)

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myid", lambda update, context: update.message.reply_text(f"Your ID: {update.effective_user.id}")))
    
    # Add admin commands
    application.add_handler(CommandHandler("admin_stats", admin_stats))
    application.add_handler(CommandHandler("lookup_user", lookup_user))
    application.add_handler(CommandHandler("whitelist", whitelist_user))
    
    # Add referral command
    application.add_handler(CommandHandler("referral", referral_command))
    
    # on non-command i.e. message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Set up webhook
    webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    logger.info(f"Setting webhook to {webhook_url}")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH.lstrip('/'),
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main() 