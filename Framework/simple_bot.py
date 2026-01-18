import requests
import logging
import json
from flask import Flask, request
from config import BOT_TOKEN, WEBHOOK_HOST, WEBHOOK_PATH, PORT, DEPOSIT_ADDRESS, REQUIRED_PAYMENT
from database import Database

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
db = Database('translucent_bot.db')

def send_message(chat_id, text, reply_markup=None):
    """Send a message to a Telegram chat"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
        
    response = requests.post(url, json=payload)
    return response.json()

def get_start_keyboard(is_premium=False):
    """Get the main keyboard for the start command"""
    if is_premium:
        keyboard = {
            'inline_keyboard': [
                [{'text': '💰 Wallet Management', 'callback_data': 'wallet_menu'}],
                [{'text': '🔄 Referral Program', 'callback_data': 'referral_menu'}]
            ]
        }
    else:
        keyboard = {
            'inline_keyboard': [
                [{'text': '💰 Link Wallet', 'callback_data': 'wallet_menu'}],
                [{'text': '💸 Pay Now', 'callback_data': 'pay_now'}],
                [{'text': '🔄 Referral Program', 'callback_data': 'referral_menu'}]
            ]
        }
    
    return keyboard

def get_wallet_management_keyboard(wallets=None):
    """Get keyboard for wallet management"""
    keyboard = {
        'inline_keyboard': [
            [{'text': '➕ Add Wallet', 'callback_data': 'add_wallet'}]
        ]
    }
    
    # Remove wallet button (only if user has wallets)
    if wallets and len(wallets) > 0:
        keyboard['inline_keyboard'].append(
            [{'text': '➖ Remove Wallet', 'callback_data': 'remove_wallet'}]
        )
    
    # Pay now button
    keyboard['inline_keyboard'].append(
        [{'text': '💸 Pay Now', 'callback_data': 'pay_now'}]
    )
    
    # Back button
    keyboard['inline_keyboard'].append(
        [{'text': '🔙 Back', 'callback_data': 'back_to_start'}]
    )
    
    return keyboard

def handle_start_command(chat_id, user_id):
    """Handle /start command"""
    # Store user in database if not exists
    username = db.get_user(user_id)['username'] if db.get_user(user_id) else None
    db.add_user_if_not_exists(user_id, username)
    
    # Get user info
    user = db.get_user(user_id)
    is_premium = user and user['is_premium']
    
    if is_premium:
        # User is premium, show premium welcome
        wallets = db.get_user_wallets(user_id)
        wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:6]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
        
        text = (
            "🌟 <b>Welcome to Translucent Premium!</b> 🌟\n\n"
            "You have full access to all premium features.\n\n"
            f"Your Linked Wallets:\n{wallet_text if wallets else 'No wallets linked yet.'}"
        )
    else:
        # User is not premium, show regular welcome
        text = (
            "👋 <b>Welcome to Translucent!</b>\n\n"
            "To access premium features, please link your wallet and make a payment."
        )
    
    # Create keyboard
    keyboard = get_start_keyboard(is_premium)
    
    send_message(chat_id, text, keyboard)

def answer_callback_query(query_id, text=None, show_alert=False):
    """Answer a callback query to stop the loading animation"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    payload = {'callback_query_id': query_id}
    
    if text:
        payload['text'] = text
        payload['show_alert'] = show_alert
        
    response = requests.post(url, json=payload)
    return response.json()

def edit_message(chat_id, message_id, text, reply_markup=None):
    """Edit a message"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
        
    response = requests.post(url, json=payload)
    return response.json()

def handle_wallet_menu(chat_id, message_id, user_id):
    """Handle wallet menu button click"""
    # Get user's wallets
    wallets = db.get_user_wallets(user_id)
    
    if wallets:
        wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:6]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
        text = f"💰 <b>Wallet Management</b> 💰\n\nYour linked wallets:\n\n{wallet_text}"
    else:
        text = "💰 <b>Wallet Management</b> 💰\n\nYou don't have any wallets linked yet. Add a wallet to continue."
    
    keyboard = get_wallet_management_keyboard(wallets)
    
    edit_message(chat_id, message_id, text, keyboard)

def handle_add_wallet(chat_id, message_id, user_id):
    """Handle add wallet button click"""
    text = (
        "Please send your Solana wallet address.\n\n"
        "Make sure it's a valid Solana address that you own."
    )
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔙 Back', 'callback_data': 'wallet_menu'}]
        ]
    }
    
    edit_message(chat_id, message_id, text, keyboard)
    
    # Store state in database
    db.set_user_state(user_id, 'ADD_WALLET')

def handle_wallet_input(chat_id, user_id, text):
    """Handle wallet address input"""
    # Validate wallet address
    if validate_solana_address(text):
        # Add wallet to database
        db.add_wallet(user_id, text)
        
        # Reset state
        db.set_user_state(user_id, None)
        
        # Send confirmation
        message = (
            f"✅ Wallet added successfully!\n\n"
            f"Address: <code>{text[:6]}...{text[-4:]}</code>"
        )
        
        keyboard = get_wallet_management_keyboard(db.get_user_wallets(user_id))
        
        send_message(chat_id, message, keyboard)
    else:
        send_message(
            chat_id, 
            "❌ Invalid Solana address. Please try again with a valid address."
        )

def validate_solana_address(address):
    """Basic validation for Solana addresses"""
    import re
    # Solana addresses are base58 encoded and typically 32-44 characters
    return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))

def handle_pay_now(chat_id, message_id, user_id):
    """Handle pay now button click"""
    # Get user's wallets
    wallets = db.get_user_wallets(user_id)
    
    if not wallets:
        text = (
            "⚠️ You need to link a wallet before making a payment.\n\n"
            "Please link your Solana wallet first, then you can proceed with payment."
        )
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🔗 Link Wallet', 'callback_data': 'wallet_menu'}]
            ]
        }
        
        edit_message(chat_id, message_id, text, keyboard)
        return
    
    wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:6]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
    
    text = (
        f"💸 <b>Payment Information</b> 💸\n\n"
        f"Please send <b>{REQUIRED_PAYMENT} SOL</b> to the following address:\n\n"
        f"<code>{DEPOSIT_ADDRESS}</code>\n\n"
        f"Important:\n"
        f"• Send exactly {REQUIRED_PAYMENT} SOL\n"
        f"• This is a one-time payment for lifetime access to Translucent\n"
        f"• Only send from your linked wallets\n"
        f"• Payment will be automatically detected\n\n"
        f"Your Linked Wallets:\n{wallet_text}"
    )
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔄 Check Payment Status', 'callback_data': 'check_payment'}],
            [{'text': '🔙 Back to Menu', 'callback_data': 'back_to_start'}]
        ]
    }
    
    edit_message(chat_id, message_id, text, keyboard)

def handle_check_payment(chat_id, message_id, user_id):
    """Handle check payment status button click"""
    # Get user info
    user = db.get_user(user_id)
    
    if user and user['is_premium']:
        # User is premium
        payments = db.get_all_payments()
        user_payments = [p for p in payments if p['telegram_id'] == user_id]
        latest_payment = user_payments[0] if user_payments else None
        
        if latest_payment:
            text = (
                f"✅ Payment received!\n\n"
                f"Amount: {latest_payment['amount']} SOL\n"
                f"Transaction ID: {latest_payment['transaction_id'][:6]}...{latest_payment['transaction_id'][-4:]}\n"
                f"Date: {latest_payment['payment_date']}\n\n"
                f"You now have lifetime access to Translucent! Thank you for your payment."
            )
        else:
            text = (
                f"✅ You have premium access to Translucent.\n\n"
                f"No payment details found in the database."
            )
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🏠 Main Menu', 'callback_data': 'back_to_start'}]
            ]
        }
        
        edit_message(chat_id, message_id, text, keyboard)
    else:
        # User is not premium
        from config import REQUIRED_PAYMENT
        remaining = REQUIRED_PAYMENT - (user['paid_amount'] if user else 0)
        
        text = (
            f"🔄 Checking payment status...\n\n"
            f"❌ No payment detected yet.\n\n"
            f"Please send {remaining} SOL to complete your payment.\n\n"
            f"If you've already sent the payment, please wait a few minutes for it to be processed."
        )
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🔄 Check Again', 'callback_data': 'check_payment'}],
                [{'text': '🔙 Back to Payment Instructions', 'callback_data': 'pay_now'}]
            ]
        }
        
        edit_message(chat_id, message_id, text, keyboard)

def get_referral_keyboard(has_referral=False):
    """Get the main keyboard for the referral command"""
    if has_referral:
        keyboard = {
            'inline_keyboard': [
                [{'text': 'View Detailed Stats', 'callback_data': 'view_detailed_stats'}],
                [{'text': 'Change Payout Wallet', 'callback_data': 'change_payout_wallet'}],
                [{'text': '🔙 Back to Menu', 'callback_data': 'back_to_start'}]
            ]
        }
    else:
        keyboard = {
            'inline_keyboard': [
                [{'text': 'Create Referral Link', 'callback_data': 'create_referral'}],
                [{'text': '🔙 Back to Menu', 'callback_data': 'back_to_start'}]
            ]
        }
    
    return keyboard

def handle_referral_command(chat_id, user_id):
    """Handle /referral command"""
    # Check if user already has a referral code
    referral_code = db.get_referral_code(user_id)
    
    if referral_code:
        # User already has a referral code, show stats
        stats = db.get_referral_stats(user_id)
        
        text = (
            f"🔄 <b>Your Referral Link</b> 🔄\n\n"
            f"Share this link with friends: https://t.me/your_bot_username?start=ref_{referral_code}\n\n"
            f"Stats:\n"
            f"• Total referrals: {stats['total_referrals']}\n"
            f"• Converted referrals: {stats['converted_referrals']}\n"
            f"• Commission earned: {stats['total_commission']} SOL"
        )
    else:
        text = (
            f"🔄 <b>Referral Program</b> 🔄\n\n"
            f"You don't have a referral code yet. Create one to start earning commissions!"
        )
    
    keyboard = get_referral_keyboard(referral_code is not None)
    
    send_message(chat_id, text, keyboard)

def handle_referral_menu(chat_id, message_id, user_id):
    """Handle referral menu button click"""
    # Similar to handle_referral_command but edit message instead
    referral_code = db.get_referral_code(user_id)
    
    if referral_code:
        # User already has a referral code, show stats
        stats = db.get_referral_stats(user_id)
        
        text = (
            f"🔄 <b>Your Referral Link</b> 🔄\n\n"
            f"Share this link with friends: https://t.me/your_bot_username?start=ref_{referral_code}\n\n"
            f"Stats:\n"
            f"• Total referrals: {stats['total_referrals']}\n"
            f"• Converted referrals: {stats['converted_referrals']}\n"
            f"• Commission earned: {stats['total_commission']} SOL"
        )
    else:
        text = (
            f"🔄 <b>Referral Program</b> 🔄\n\n"
            f"You don't have a referral code yet. Create one to start earning commissions!"
        )
    
    keyboard = get_referral_keyboard(referral_code is not None)
    
    edit_message(chat_id, message_id, text, keyboard)

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """Handle Telegram webhook updates"""
    try:
        update = request.json
        logger.info(f"Received Telegram update: {json.dumps(update, indent=2)}")
        
        # Process the update
        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            
            # Handle commands
            if 'text' in message:
                text = message['text']
                
                if text.startswith('/start'):
                    # Handle start command
                    handle_start_command(chat_id, user_id)
                    
                elif text.startswith('/help'):
                    # Handle help command
                    send_message(chat_id, "Available commands:\n/start - Start the bot\n/help - Show this help message\n/myid - Show your Telegram ID")
                    
                elif text.startswith('/myid'):
                    # Handle myid command
                    send_message(chat_id, f"Your Telegram ID is: {user_id}")
                    
                elif text.startswith('/referral'):
                    # Handle referral command
                    handle_referral_command(chat_id, user_id)
                    
                else:
                    # Check if user is in a state waiting for input
                    state = db.get_user_state(user_id)
                    if state == 'ADD_WALLET':
                        handle_wallet_input(chat_id, user_id, text)
                    else:
                        # Echo the message
                        send_message(chat_id, f"You said: {text}")
        
        # Handle callback queries (button clicks)
        elif 'callback_query' in update:
            callback_query = update['callback_query']
            query_id = callback_query['id']
            chat_id = callback_query['message']['chat']['id']
            message_id = callback_query['message']['message_id']
            user_id = callback_query['from']['id']
            data = callback_query['data']
            
            # Answer callback query to stop loading animation
            answer_callback_query(query_id)
            
            # Handle different callback data
            if data == 'wallet_menu':
                handle_wallet_menu(chat_id, message_id, user_id)
            elif data == 'add_wallet':
                handle_add_wallet(chat_id, message_id, user_id)
            elif data == 'back_to_start':
                handle_start_command(chat_id, user_id)
                edit_message(chat_id, message_id, "Returning to main menu...")
            elif data == 'pay_now':
                handle_pay_now(chat_id, message_id, user_id)
            elif data == 'check_payment':
                handle_check_payment(chat_id, message_id, user_id)
            elif data == 'referral_menu':
                handle_referral_menu(chat_id, message_id, user_id)
        
        return '', 200
    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}", exc_info=True)
        return '', 500

@app.route('/', methods=['GET'])
def index():
    """Simple route to check if the server is running"""
    return "Telegram bot webhook server is running"

if __name__ == '__main__':
    # Set the webhook
    webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    set_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    
    logger.info(f"Setting webhook to {webhook_url}")
    response = requests.get(set_webhook_url)
    logger.info(f"Webhook set response: {response.json()}")
    
    # Make sure the payment webhook server is running
    logger.info("Make sure to run webhook_server.py in a separate terminal for payment processing")
    
    # Run the Flask app
    logger.info(f"Starting Telegram webhook server on port {PORT}")
    app.run(host='0.0.0.0', port=PORT) 