import requests
import logging
import json
import re
import time
import os
import datetime
import jwt
from flask import Flask, request, jsonify, send_from_directory, redirect
from config import BOT_TOKEN, WEBHOOK_HOST, WEBHOOK_PATH, PAYMENT_WEBHOOK_PATH, PORT, DEPOSIT_ADDRESS, REQUIRED_PAYMENT, COMMISSION_PERCENTAGE, ADMIN_IDS, AUTH_TOKEN_EXPIRY, AUTH_SERVER_URL, WEBSITE_URL
from database import Database
from flask_cors import CORS
from auth_routes import setup_auth_routes
from dotenv import load_dotenv
from keyboards.start_keyboards import get_start_keyboard, get_wallet_management_keyboard
from keyboards.referral_keyboards import get_referral_keyboard, get_referral_stats_keyboard

# Load environment variables from .env file (in development)
load_dotenv()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define paths to React build directories
LANDING_PAGE_BUILD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Webs', 'landing', 'build')
PREMIUM_PAGE_BUILD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Webs', 'premium', 'build')

print(f"Looking for Landing Page build files in: {LANDING_PAGE_BUILD_DIR}")
print(f"Directory exists: {os.path.exists(LANDING_PAGE_BUILD_DIR)}")
print(f"Looking for Premium Page build files in: {PREMIUM_PAGE_BUILD_DIR}")
print(f"Directory exists: {os.path.exists(PREMIUM_PAGE_BUILD_DIR)}")

# Now create the Flask app with the static_folder parameter for the landing page
# We'll handle premium page static files separately
app = Flask(__name__, static_folder=os.path.join(LANDING_PAGE_BUILD_DIR, 'static'))
db = Database('translucent_bot.db')

# Enable CORS for the app
CORS(app)

# Setup authentication routes
setup_auth_routes(app)

# Use webhook URL from config
webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Add this helper function after the imports
def convert_keyboard_to_dict(keyboard_markup):
    """Convert keyboard to raw dictionary format if needed"""
    if not keyboard_markup:
        return None
    
    # If it's already a dict, return as is
    if isinstance(keyboard_markup, dict):
        return keyboard_markup
    
    # Otherwise convert from InlineKeyboardMarkup
    keyboard = {'inline_keyboard': []}
    for row in keyboard_markup.inline_keyboard:
        keyboard_row = []
        for button in row:
            button_dict = {
                'text': button.text,
                'callback_data': button.callback_data
            }
            if hasattr(button, 'url') and button.url:
                button_dict['url'] = button.url
            keyboard_row.append(button_dict)
        keyboard['inline_keyboard'].append(keyboard_row)
    return keyboard

# --- Telegram Bot Functions ---

def send_message(chat_id, text, reply_markup=None):
    """Send a message to a chat"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(convert_keyboard_to_dict(reply_markup))
    
    try:
        response = requests.post(url, json=payload)
        if not response.ok:
            logger.error(f"Error sending message: {response.text}")
        
        return response.json()
    except Exception as e:
        logger.error(f"Exception sending message: {e}")
        return {"ok": False, "error": str(e)}

def handle_start_command(chat_id, user_id, username=None, start_param=None):
    """Handle /start command"""
    try:
        # Store user in database if not exists
        db.add_user_if_not_exists(user_id, username)
        
        # Handle referral parameter silently in the background
        if start_param and start_param.startswith('ref_'):
            try:
                referral_code = start_param[4:]  # Remove 'ref_' prefix
                logger.info(f"Processing referral code: {referral_code}")
                
                # Get referrer user ID safely
                referrer_id = None
                try:
                    # Get the user who created this referral code
                    referrer_id = db.get_user_by_referral_code(referral_code)
                    logger.info(f"Found referrer ID: {referrer_id} for code: {referral_code}")
                    
                    if not referrer_id:
                        logger.warning(f"No user found with referral code: {referral_code}")
                except Exception as e:
                    logger.error(f"Error getting referrer ID: {e}")
                
                # Record referral relationship if valid (silently)
                if referrer_id and referrer_id != user_id:  # Prevent self-referrals
                    try:
                        success = db.record_referral(referrer_id, user_id)
                        logger.info(f"Recorded referral: {referrer_id} referred {user_id}, success: {success}")
                    except Exception as e:
                        logger.error(f"Error recording referral: {e}")
            except Exception as e:
                logger.error(f"Error processing referral parameter: {e}")
                # Continue with normal start command even if referral processing fails
        
        # Special case for web_auth parameter
        if start_param == 'web_auth':
            # Generate auth token and send link with button
            auth_token = db.generate_auth_token(user_id, AUTH_TOKEN_EXPIRY)
            if auth_token:
                auth_url = f"{WEBHOOK_HOST}?token={auth_token['token']}"
                keyboard = {
                    'inline_keyboard': [
                        [{'text': '🌐 Access Website', 'url': auth_url}]
                    ]
                }
                send_message(
                    chat_id,
                    f"🔗 <b>Website Authentication</b> 🔗\n\n"
                    f"Click the button below to access the Translucent website with your account:",
                    keyboard
                )
                return
            else:
                send_message(chat_id, "❌ Failed to generate authentication token. Please try again.")
                return
        
        # Get user info - same for all users regardless of referral
        user = db.get_user(user_id)
        is_premium = user and user['is_premium']
        
        # Show appropriate welcome message based on premium status only
        if is_premium:
            # User is premium, show premium welcome with new format
            text = (
                "⭐👁️ <b>Translucent Lifetime Access</b>\n\n"
                "🎯 The only trading database for finding wallets to track and copy trade across 5 networks\n"
                "[ SOL, ETH, BASE, TRON, BSC ]\n\n"
                "🌐 Twitter/X: <a href='https://twitter.com/translucentrade'>@translucentrade</a>\n"
                "🟢 Trade on all chains via <a href='https://t.me/gmgnaibot?start=i_iuGhO47u'>GMGN.ai</a>\n"
                "✏️ Contact the developer: <a href='https://x.com/toursoflife'>@toursoflife</a>\n\n"
                "👁️ To access the website and login, please click the button below. Links expire, and are not intended to be shared for security reasons\n\n"
                "💰 The referral program is available. Click the button below to setup/manage your referrals\n\n"
                "Thank you for using Translucent"
            )
        else:
            # User is not premium, show regular welcome with new format
            text = (
                "👁️ <b>Welcome to Translucent</b>\n\n"
                "🎯 The only trading database for finding wallets to track and copy trade across 5 networks\n"
                "[ SOL, ETH, BASE, TRON, BSC ]\n\n"
                "🌐 Twitter/X: <a href='https://twitter.com/translucentrade'>@translucentrade</a>\n"
                "🟢 Trade on all chains via <a href='https://t.me/gmgnaibot?start=i_iuGhO47u'>GMGN.ai</a>\n"
                "✏️ Contact the developer: <a href='https://x.com/toursoflife'>@toursoflife</a>\n\n"
                "👁️ <b>How to access the website</b>\n\n"
                "We offer lifetime access for 0.5 solana. Link the wallet you are paying from and then click pay now. Web access will be granted automatically\n\n"
                "💰 The referral program is available to everybody. Visit the referral program by clicking the button below"
            )
        
        # Create keyboard - same for all users based only on premium status
        keyboard = get_start_keyboard(is_premium)
        
        send_message(chat_id, text, keyboard)
    except Exception as e:
        logger.error(f"Error in handle_start_command: {e}", exc_info=True)
        # Send a simple message to avoid leaving the user hanging
        send_message(
            chat_id,
            "Welcome to Translucent! Please try the /start command again if you encounter any issues."
        )

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
        payload['reply_markup'] = json.dumps(convert_keyboard_to_dict(reply_markup))
    
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

def handle_wallet_input(chat_id, user_id, text, message_id=None):
    """Handle wallet address input"""
    # Validate wallet address
    if validate_solana_address(text):
        # Add wallet to database
        success = db.add_wallet(user_id, text)
        
        # Reset state
        db.set_user_state(user_id, None)
        
        if success:
            # Get updated wallets
            wallets = db.get_user_wallets(user_id)
            
            # Format wallet list
            wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:6]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
            
            text = (
                f"💰 <b>Wallet Management</b> 💰\n\n"
                f"✅ Wallet added successfully!\n\n"
                f"Your linked wallets:\n\n{wallet_text}"
            )
            
            keyboard = get_wallet_management_keyboard(wallets)
            
            if message_id:
                edit_message(chat_id, message_id, text, keyboard)
            else:
                send_message(chat_id, text, keyboard)
        else:
            error_text = "❌ Failed to add wallet. This wallet might already be linked."
            if message_id:
                edit_message(chat_id, message_id, error_text)
            else:
                send_message(chat_id, error_text)
    else:
        error_text = "❌ Invalid Solana address. Please try again with a valid address."
        if message_id:
            edit_message(chat_id, message_id, error_text)
        else:
            send_message(chat_id, error_text)

def validate_solana_address(address):
    """Basic validation for Solana addresses"""
    # Solana addresses are base58 encoded and typically 32-44 characters
    return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))

def handle_pay_now(chat_id, message_id, user_id):
    """Handle pay now button click"""
    # Get user information
    user = db.get_user(user_id)
    
    if user and user['is_premium']:
        # User is already premium
        edit_message(chat_id, message_id, "You are already a premium user! 🌟")
        return
    
    # Get user wallets
    wallets = db.get_user_wallets(user_id)
    
    if not wallets:
        # User has no wallets
        keyboard = {
            'inline_keyboard': [
                [{'text': '💳 Link a Wallet First', 'callback_data': 'wallet_menu'}],
                [{'text': '🔙 Back', 'callback_data': 'back_to_start'}]
            ]
        }
        
        edit_message(chat_id, message_id, "You need to link a wallet before you can pay.", keyboard)
        return
    
    # Get user's payment amount if any
    paid_amount = user['paid_amount'] if user else 0
    remaining_amount = max(0, REQUIRED_PAYMENT - paid_amount)
    
    # Format wallet list
    wallet_list = "\n".join([f"• <code>{w['solana_address']}</code>" for w in wallets])
    
    # Create payment instructions
    text = (
        f"💰 <b>Payment Instructions</b> 💰\n\n"
        f"Please send at least {remaining_amount:.3f} SOL from one of your linked wallets to:\n\n"
        f"<code>{DEPOSIT_ADDRESS}</code>\n\n"
        f"Important:\n"
        f"• You need to send at least {REQUIRED_PAYMENT:.3f} SOL total for premium access\n"
        f"• You've already paid {paid_amount:.3f} SOL\n"
        f"• You can send more than the required amount if you wish\n"
        f"• Only send from your linked wallets\n\n"
        f"Your linked wallets:\n{wallet_list}"
    )
    
    # Create keyboard with back button only
    keyboard = {
        'inline_keyboard': [
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
        payments = db.get_payment_history(user_id)
        latest_payment = payments[0] if payments else None
        
        if latest_payment:
            text = (
                f"✅ <b>Payment Confirmed!</b>\n\n"
                f"Total paid: {user['paid_amount']:.3f} SOL\n"
                f"Latest payment: {latest_payment['amount']:.3f} SOL\n"
                f"Date: {latest_payment['payment_date']}\n\n"
                f"You have full access to all premium features!"
            )
        else:
            text = (
                f"✅ <b>Premium Access Confirmed</b>\n\n"
                f"You have full access to all premium features!"
            )
    else:
        # User is not premium
        paid_amount = user['paid_amount'] if user else 0
        remaining = REQUIRED_PAYMENT - paid_amount
        
        text = (
            f"💰 <b>Payment Status</b> 💰\n\n"
            f"• Required payment: {REQUIRED_PAYMENT:.3f} SOL\n"
            f"• Total paid so far: {paid_amount:.3f} SOL\n"
            f"• Remaining amount: {remaining:.3f} SOL\n\n"
            f"Please complete your payment to gain premium access."
        )
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔄 Refresh Status', 'callback_data': 'check_payment'}],
            [{'text': '🔙 Back to Menu', 'callback_data': 'back_to_start'}]
        ]
    }
    
    edit_message(chat_id, message_id, text, keyboard)

def handle_referral_menu(chat_id, message_id, user_id):
    """Handle referral menu button click"""
    # Similar to handle_referral_command but edit message instead
    referral_code = db.get_referral_code(user_id)
    
    if referral_code:
        # User already has a referral code, show stats
        stats = db.get_referral_stats(user_id)
        
        # Get current payout wallet from the user record
        user_data = db.get_user(user_id)
        payout_wallet = user_data.get('payout_wallet') if user_data else None
        wallet_text = f"Current payout wallet: <code>{payout_wallet[:6]}...{payout_wallet[-4:]}</code>" if payout_wallet else "No payout wallet set yet. Please set one to receive commissions."
        
        text = (
            f"🔄 <b>Your Referral Link</b> 🔄\n\n"
            f"https://t.me/translucent_trade_bot?start=ref_{referral_code}\n\n"
            f"Share this link, or add it to your social media account and begin earning payouts for users onboarded\n\n"
            f"Please remember to add/change your payout wallet [ Solana receiving address ]\n\n"
            f"{wallet_text}\n\n"
            f"Stats:\n"
            f"• Total referrals: {stats['total_referrals']}\n"
            f"• Converted referrals: {stats['converted_referrals']}\n"
            f"• Commission earned: {stats['total_commission']} SOL"
        )
    else:
        text = (
            f"💰 <b>Translucent Referrals</b>\n\n"
            f"Welcome to Translucent's referral program\n\n"
            f"🔔 It appears you have not made your custom referral link yet. To create a link and start earning payouts please click the button below"
        )
    
    keyboard = get_referral_keyboard(referral_code is not None)
    
    edit_message(chat_id, message_id, text, keyboard)

def handle_remove_wallet(chat_id, message_id, user_id):
    """Handle remove wallet button click"""
    # Get user's wallets
    wallets = db.get_user_wallets(user_id)
    
    if not wallets:
        text = "You don't have any wallets to remove."
        keyboard = get_wallet_management_keyboard(wallets)
        edit_message(chat_id, message_id, text, keyboard)
        return
    
    # Create a keyboard with all wallets as buttons
    keyboard = {
        'inline_keyboard': []
    }
    
    for i, wallet in enumerate(wallets):
        address = wallet['solana_address']
        display = f"{address[:6]}...{address[-4:]}"
        keyboard['inline_keyboard'].append([
            {'text': f"❌ {display}", 'callback_data': f"remove_wallet_{address}"}
        ])
    
    # Add back button
    keyboard['inline_keyboard'].append([
        {'text': '🔙 Back', 'callback_data': 'wallet_menu'}
    ])
    
    text = "Select a wallet to remove:"
    edit_message(chat_id, message_id, text, keyboard)

def handle_remove_specific_wallet(chat_id, message_id, user_id, wallet_address):
    """Handle removing a specific wallet"""
    # Remove the wallet from the database
    success = db.remove_wallet(user_id, wallet_address)
    
    if success:
        text = f"✅ Wallet removed successfully: {wallet_address[:6]}...{wallet_address[-4:]}"
    else:
        text = f"❌ Failed to remove wallet: {wallet_address[:6]}...{wallet_address[-4:]}"
    
    # Get updated wallets
    wallets = db.get_user_wallets(user_id)
    keyboard = get_wallet_management_keyboard(wallets)
    
    edit_message(chat_id, message_id, text, keyboard)

def handle_create_referral(chat_id, message_id, user_id):
    """Handle create referral link button click"""
    text = (
        "Please enter a referral code (3-15 characters).\n\n"
        "Rules:\n"
        "• Only letters, numbers, and underscores (_)\n"
        "• 3-15 characters in length\n"
        "• Must be unique\n\n"
        "This code will be part of your referral link."
    )
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔙 Back', 'callback_data': 'referral_menu'}]
        ]
    }
    
    edit_message(chat_id, message_id, text, keyboard)
    
    # Store state in database
    db.set_user_state(user_id, 'CREATE_REFERRAL')

def handle_referral_code_input(chat_id, user_id, text, message_id=None):
    """Handle referral code input"""
    # Validate and create referral code
    if validate_referral_code(text):
        # Add referral code to database
        success = db.create_referral_code(user_id, text)
        
        if success:
            # Reset state
            db.set_user_state(user_id, None)
            
            # Get referral stats
            stats = db.get_referral_stats(user_id)
            
            # Get current payout wallet
            user_data = db.get_user(user_id)
            payout_wallet = user_data.get('payout_wallet') if user_data else None
            wallet_text = f"Current payout wallet: <code>{payout_wallet[:6]}...{payout_wallet[-4:]}</code>" if payout_wallet else "No payout wallet set yet. Please set one to receive commissions."
            
            # Create confirmation message
            referral_link = f"https://t.me/translucent_trade_bot?start=ref_{text}"
            text = (
                f"🔄 <b>Your Referral Link</b> 🔄\n\n"
                f"{referral_link}\n\n"
                f"Share this link, or add it to your social media account and begin earning payouts for users onboarded\n\n"
                f"Please remember to add/change your payout wallet [ Solana receiving address ]\n\n"
                f"{wallet_text}\n\n"
                f"Stats:\n"
                f"• Total referrals: {stats['total_referrals']}\n"
                f"• Converted referrals: {stats['converted_referrals']}\n"
                f"• Commission earned: {stats['total_commission']} SOL"
            )
            
            keyboard = get_referral_keyboard(True)
            
            if message_id:
                edit_message(chat_id, message_id, text, keyboard)
            else:
                send_message(chat_id, text, keyboard)
        else:
            error_text = "❌ Failed to create referral code. This code might already be taken. Please try another one."
            if message_id:
                edit_message(chat_id, message_id, error_text)
            else:
                send_message(chat_id, error_text)
    else:
        error_text = "❌ Invalid referral code. Please use only letters, numbers, and underscores (3-15 characters)."
        if message_id:
            edit_message(chat_id, message_id, error_text)
        else:
            send_message(chat_id, error_text)

def validate_referral_code(code):
    """Validate referral code"""
    return re.match(r'^[a-zA-Z0-9_]{3,15}$', code) is not None

def handle_change_payout_wallet(chat_id, message_id, user_id):
    """Handle change payout wallet button click"""
    # Get current payout wallet
    payout_wallet = db.get_payout_wallet(user_id)
    
    current_wallet = f"\n\nCurrent payout wallet: <code>{payout_wallet[:6]}...{payout_wallet[-4:]}</code>" if payout_wallet else ""
    
    text = (
        f"💳 Please enter the solana address where you would like to receive referral payments from now on{current_wallet}"
    )
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔙 Back', 'callback_data': 'referral_menu'}]
        ]
    }
    
    edit_message(chat_id, message_id, text, keyboard)
    
    # Store state in database
    db.set_user_state(user_id, 'SET_PAYOUT_WALLET')

def handle_payout_wallet_input(chat_id, user_id, text, message_id=None):
    """Handle payout wallet input"""
    # Validate wallet address
    if validate_solana_address(text):
        # Set payout wallet
        success = db.set_payout_wallet(user_id, text)
        
        # Reset state
        db.set_user_state(user_id, None)
        
        if success:
            # Get referral stats
            stats = db.get_referral_stats(user_id)
            referral_code = db.get_referral_code(user_id)
            
            # Create confirmation message
            text = (
                f"🔄 <b>Your Referral Link</b> 🔄\n\n"
                f"https://t.me/translucent_trade_bot?start=ref_{referral_code}\n\n"
                f"Share this link, or add it to your social media account and begin earning payouts for users onboarded\n\n"
                f"✅ Payout wallet updated successfully!\n"
                f"Current payout wallet: <code>{text[:6]}...{text[-4:]}</code>\n\n"
                f"Stats:\n"
                f"• Total referrals: {stats['total_referrals']}\n"
                f"• Converted referrals: {stats['converted_referrals']}\n"
                f"• Commission earned: {stats['total_commission']} SOL"
            )
            
            keyboard = get_referral_keyboard(has_referral=True)
            
            if message_id:
                edit_message(chat_id, message_id, text, keyboard)
            else:
                send_message(chat_id, text, keyboard)
        else:
            error_text = "❌ Failed to set payout wallet. Please try again later."
            if message_id:
                edit_message(chat_id, message_id, error_text)
            else:
                send_message(chat_id, error_text)
    else:
        error_text = "❌ Invalid Solana address. Please try again with a valid address."
        if message_id:
            edit_message(chat_id, message_id, error_text)
        else:
            send_message(chat_id, error_text)

def handle_view_detailed_stats(chat_id, message_id, user_id):
    """Handle view detailed stats button click"""
    # Get referral data
    referrals = db.get_user_referrals(user_id)
    stats = db.get_referral_stats(user_id)
    
    if not referrals:
        text = "You don't have any referrals yet."
    else:
        # Format referral data
        referral_text = ""
        for i, ref in enumerate(referrals[:10]):  # Show only first 10
            status = "✅ Paid" if ref['converted'] else "⏳ Pending"
            date = ref['referral_date'].split('T')[0] if 'T' in ref['referral_date'] else ref['referral_date']
            commission = f" (+{ref['commission_owed']:.3f} SOL)" if ref['converted'] else ""
            
            referral_text += f"{i+1}. {status}{commission} - {date}\n"
        
        if len(referrals) > 10:
            referral_text += f"\n...and {len(referrals) - 10} more"
        
        # Calculate conversion rate
        conversion_rate = (stats['converted_referrals'] / stats['total_referrals'] * 100) if stats['total_referrals'] > 0 else 0
        
        text = (
            f"📊 <b>Detailed Referral Stats</b> 📊\n\n"
            f"Summary:\n"
            f"• Total referral clicks: {stats['total_referrals']}\n"
            f"• Converted to premium: {stats['converted_referrals']}\n"
            f"• Conversion rate: {conversion_rate:.1f}%\n"
            f"• Total commission: {stats['total_commission']:.3f} SOL\n\n"
            f"Recent referrals:\n{referral_text}"
        )
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔙 Back to Referrals', 'callback_data': 'referral_menu'}]
        ]
    }
    
    edit_message(chat_id, message_id, text, keyboard)

def handle_access_website(chat_id, message_id, user_id):
    """Handle website access button click"""
    # Check if user is premium
    user = db.get_user(user_id)
    
    if not user or not user['is_premium']:
        text = (
            "⚠️ <b>Premium Access Required</b> ⚠️\n\n"
            "You need to be a premium user to access the website.\n"
            "Please make a payment to unlock premium features."
        )
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '💸 Pay Now', 'callback_data': 'pay_now'}],
                [{'text': '🔙 Back to Menu', 'callback_data': 'back_to_start'}]
            ]
        }
        
        edit_message(chat_id, message_id, text, keyboard)
        return
    
    # Generate authentication token
    token_data = db.generate_auth_token(user_id, expiry_minutes=AUTH_TOKEN_EXPIRY)
    
    if not token_data:
        text = (
            "❌ <b>Error</b> ❌\n\n"
            "Failed to generate access link. Please try again later."
        )
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🔙 Back to Menu', 'callback_data': 'back_to_start'}]
            ]
        }
        
        edit_message(chat_id, message_id, text, keyboard)
        return
    
    # Create authentication URL
    auth_url = f"{AUTH_SERVER_URL}/auth?token={token_data['token']}"
    
    # Calculate expiration time in minutes
    expires_in = int((token_data['expires_at'] - time.time()) / 60)
    
    text = (
        "🌐 <b>Website Access</b> 🌐\n\n"
        "Click the button below to access the website:\n\n"
        f"⏱️ This link will expire in {expires_in} minutes.\n"
        "🔒 This link can only be used once."
    )
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔗 Access Website', 'url': auth_url}],
            [{'text': '🔄 Generate New Link', 'callback_data': 'access_website'}],
            [{'text': '🔙 Back to Menu', 'callback_data': 'back_to_start'}]
        ]
    }
    
    edit_message(chat_id, message_id, text, keyboard)

def handle_web_command(chat_id, user_id):
    """Handle /web command to provide website access"""
    try:
        # Generate auth token
        auth_token = db.generate_auth_token(user_id, AUTH_TOKEN_EXPIRY)
        
        if auth_token:
            # Create authentication URL
            auth_url = f"{WEBSITE_URL}?token={auth_token['token']}"
            
            # Create a keyboard with login buttons
            keyboard = {
                'inline_keyboard': [
                    [{'text': '🔐 Login to Website', 'url': auth_url}]
                ]
            }
            
            # Send a new message with login button
            send_message(
                chat_id,
                f"Seamlessly log in to your Translucent account by tapping below ⬇️",
                keyboard
            )
            
            # Log the URL for debugging
            logger.info(f"Generated auth URL: {auth_url}")
        else:
            send_message(
                chat_id,
                "❌ Failed to generate authentication token. Please try again."
            )
    except Exception as e:
        logger.error(f"Error in handle_web_command: {e}")
        send_message(chat_id, "An error occurred. Please try again later.")

def handle_website_login(chat_id, message_id, user_id):
    """Handle website login button click"""
    # Generate auth token
    auth_token = db.generate_auth_token(user_id, AUTH_TOKEN_EXPIRY)
    
    if auth_token:
        # Create authentication URL using the ngrok URL
        auth_url = f"{WEBHOOK_HOST}?token={auth_token['token']}"
        
        # Send a new message with the login button
        keyboard = {
            'inline_keyboard': [
                [{'text': '🔐 Login to Website', 'url': auth_url}]
            ]
        }
        
        send_message(
            chat_id,
            f"Seamlessly log in to your Translucent account by tapping below ⬇️",
            keyboard
        )
        
        logger.info(f"Generated auth URL: {auth_url}")
    else:
        send_message(chat_id, "❌ Failed to generate authentication token. Please try again.")

def handle_debug_referrals(chat_id, user_id):
    """Debug referral system (admin only)"""
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        send_message(chat_id, "⛔ You don't have permission to use this command.")
        return
    
    # Get debug info
    debug_info = db.debug_referrals()
    
    if 'error' in debug_info:
        send_message(chat_id, f"❌ Error: {debug_info['error']}")
        return
    
    # Format referrals
    referrals_text = "No referrals found."
    if debug_info['referrals']:
        referrals_text = "\n".join([
            f"{r['id']}: {r['referrer_id']} → {r['referred_id']} ({r['referral_date'][:10]}) {'✅' if r['converted'] else '⏳'}"
            for r in debug_info['referrals'][:10]  # Show first 10
        ])
        if len(debug_info['referrals']) > 10:
            referrals_text += f"\n...and {len(debug_info['referrals']) - 10} more"
    
    # Format codes
    codes_text = "No referral codes found."
    if debug_info['codes']:
        codes_text = "\n".join([
            f"{c['telegram_id']}: {c['code']}"
            for c in debug_info['codes'][:10]  # Show first 10
        ])
        if len(debug_info['codes']) > 10:
            codes_text += f"\n...and {len(debug_info['codes']) - 10} more"
    
    # Send debug info
    send_message(
        chat_id,
        f"🔍 <b>Referral System Debug</b>\n\n"
        f"<b>Referrals:</b>\n{referrals_text}\n\n"
        f"<b>Referral Codes:</b>\n{codes_text}"
    )

def handle_debug_user(chat_id, user_id, target_id=None):
    """Debug user information (admin only)"""
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        send_message(chat_id, "⛔ You don't have permission to use this command.")
        return
    
    # If no target_id provided, use the admin's ID
    if not target_id:
        target_id = user_id
    
    # Get user info
    user = db.get_user(target_id)
    if not user:
        send_message(chat_id, f"❌ User {target_id} not found in database.")
        return
    
    # Get user's wallets
    wallets = db.get_user_wallets(target_id)
    wallet_text = "\n".join([f"• {w['solana_address']}" for w in wallets]) if wallets else "None"
    
    # Get payment history
    payments = db.get_payment_history(target_id)
    payment_text = "\n".join([
        f"• {p['amount']:.3f} SOL on {p['payment_date'][:10]}"
        for p in payments
    ]) if payments else "None"
    
    # Get referral info
    referrals = db.get_user_referrals(target_id)
    referral_text = f"Total: {len(referrals)}\nConverted: {sum(1 for r in referrals if r['converted'])}"
    
    # Format user info
    text = (
        f"🔍 <b>User Debug Info</b>\n\n"
        f"<b>User ID:</b> {user['telegram_id']}\n"
        f"<b>Username:</b> {user['username'] or 'None'}\n"
        f"<b>Premium:</b> {'✅ Yes' if user['is_premium'] else '❌ No'}\n"
        f"<b>Paid Amount:</b> {user['paid_amount']:.3f} SOL\n"
        f"<b>Registration Date:</b> {user['registration_date'][:10]}\n\n"
        f"<b>Wallets:</b>\n{wallet_text}\n\n"
        f"<b>Payments:</b>\n{payment_text}\n\n"
        f"<b>Referrals:</b>\n{referral_text}"
    )
    
    send_message(chat_id, text)

def handle_debug_codes(chat_id, user_id):
    """Debug referral codes (admin only)"""
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        send_message(chat_id, "⛔ You don't have permission to use this command.")
        return
    
    # Get all referral codes
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM referral_codes")
        codes = [dict(row) for row in cursor.fetchall()]
        
        if not codes:
            send_message(chat_id, "No referral codes found in the database.")
            return
        
        # Format codes
        codes_text = "\n".join([
            f"• User {c['telegram_id']}: <code>{c['code']}</code> (created: {c['created_date'][:10]})"
            for c in codes
        ])
        
        send_message(
            chat_id,
            f"🔍 <b>Referral Codes</b>\n\n{codes_text}"
        )
    except Exception as e:
        send_message(chat_id, f"❌ Error: {e}")
    finally:
        conn.close()

def handle_debug_schema(chat_id, user_id):
    """Debug database schema (admin only)"""
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        send_message(chat_id, "⛔ You don't have permission to use this command.")
        return
    
    # Get database schema
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Get tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        schema_text = ""
        
        # Get columns for each table
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [f"{row[1]} ({row[2]})" for row in cursor.fetchall()]
            schema_text += f"<b>{table}</b>:\n"
            schema_text += "\n".join([f"• {col}" for col in columns])
            schema_text += "\n\n"
        
        send_message(
            chat_id,
            f"🔍 <b>Database Schema</b>\n\n{schema_text}"
        )
    except Exception as e:
        send_message(chat_id, f"❌ Error: {e}")
    finally:
        conn.close()

# --- Payment Processing Functions ---

def process_transaction(transaction):
    """Process a single transaction"""
    try:
        # Log the entire transaction for debugging
        logger.info(f"Processing transaction: {json.dumps(transaction, indent=2)}")
        
        # Extract transaction details
        if 'signature' not in transaction:
            logger.error("Transaction missing signature")
            return
            
        transaction_id = transaction['signature']
        logger.info(f"Transaction ID: {transaction_id}")
        
        # Check for native transfers
        if 'nativeTransfers' not in transaction or not transaction['nativeTransfers']:
            logger.info(f"No native transfers in transaction {transaction_id}")
            return
            
        # Log our deposit address for comparison
        logger.info(f"Our deposit address: {DEPOSIT_ADDRESS}")
        
        # Look for transfers to our deposit address
        for transfer in transaction['nativeTransfers']:
            to_address = transfer.get('toUserAccount')
            from_address = transfer.get('fromUserAccount')
            amount_lamports = transfer.get('amount', 0)
            
            logger.info(f"Transfer: {amount_lamports} lamports from {from_address} to {to_address}")
            
            # Convert lamports to SOL (1 SOL = 1,000,000,000 lamports)
            amount_sol = amount_lamports / 1_000_000_000
            
            # Check if this is a payment to our deposit address
            if to_address == DEPOSIT_ADDRESS:
                logger.info(f"✅ Payment detected: {amount_sol} SOL from {from_address} to {to_address}")
                
                # Find the user who owns this wallet
                user_id = db.get_user_by_wallet(from_address)
                logger.info(f"Looking up user for wallet {from_address}: user_id = {user_id}")
                
                if not user_id:
                    logger.warning(f"Wallet {from_address} not associated with any user")
                    continue
                
                # Record the payment
                success = db.add_payment(user_id, transaction_id, amount_sol)
                logger.info(f"Payment recorded: {success}")
                
                if not success:
                    logger.error(f"Failed to record payment for user {user_id}")
                    continue
                
                # Get user's total paid amount
                user = db.get_user(user_id)
                paid_amount = user['paid_amount'] if user else 0
                logger.info(f"User {user_id} total paid amount: {paid_amount}")
                
                # Check if payment is sufficient for premium access
                if paid_amount >= REQUIRED_PAYMENT:
                    logger.info(f"User {user_id} has paid enough for premium access")
                    
                    # Set user to premium - IMPORTANT: Do this BEFORE processing referral
                    premium_success = db.set_premium_status(user_id, True)
                    logger.info(f"Set premium status for user {user_id}: {premium_success}")
                    
                    # Process referral if exists - this happens in the background
                    referrer_id = db.convert_referral(user_id, amount_sol, COMMISSION_PERCENTAGE)
                    logger.info(f"Processed referral for user {user_id}, referrer: {referrer_id}")
                    
                    # Send notification to user - same for all users
                    send_telegram_message(user_id, 
                        "🎉 <b>Payment Confirmed!</b> 🎉\n\n"
                        f"We have received your payment of {amount_sol:.3f} solana\n\n"
                        f"Enter /start to begin accessing Translucent's features"
                    )
                    
                    # Send notification to referrer if exists
                    if referrer_id:
                        referral_stats = db.get_referral_stats(referrer_id)
                        commission_amount = amount_sol * (COMMISSION_PERCENTAGE/100)
                        send_telegram_message(referrer_id,
                            "🎉 <b>Referral Converted!</b> 🎉\n\n"
                            f"You earned {commission_amount:.3f} SOL in commission.\n\n"
                            f"Total commission earned: {referral_stats['total_commission']:.3f} SOL"
                        )
                else:
                    # Payment is partial, send notification about remaining amount
                    remaining = REQUIRED_PAYMENT - paid_amount
                    send_telegram_message(user_id,
                        "💰 <b>Partial Payment Received</b> 💰\n\n"
                        f"• Amount received: {amount_sol:.3f} SOL\n"
                        f"• Total paid so far: {paid_amount:.3f} SOL\n"
                        f"• Remaining amount: {remaining:.3f} SOL\n\n"
                        "Please complete the payment to gain full access."
                    )
            else:
                logger.info(f"❌ Not a payment to our deposit address: {to_address} != {DEPOSIT_ADDRESS}")
    except Exception as e:
        logger.error(f"Error processing transaction: {e}", exc_info=True)

def send_telegram_message(chat_id, text):
    """Send a message to a user via Telegram API"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    logger.info(f"Sending Telegram message to {chat_id}: {text}")
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        logger.error(f"Failed to send Telegram message: {response.text}")
    else:
        logger.info(f"Telegram message sent successfully: {response.json()}")

def handle_payment_confirmation(user_id, amount, transaction_hash):
    """Handle payment confirmation from webhook"""
    try:
        # Update user's payment status
        db.update_payment(user_id, amount)
        
        # Check if user has reached the required payment amount
        user = db.get_user(user_id)
        
        if user and user['paid_amount'] >= REQUIRED_PAYMENT and not user['is_premium']:
            # User has reached the required payment amount, upgrade to premium
            db.set_premium_status(user_id, True)
            
            # Process referral commission if applicable
            referrer_id = db.get_referrer(user_id)
            if referrer_id:
                commission_amount = amount * (COMMISSION_PERCENTAGE / 100)
                db.add_commission(referrer_id, commission_amount, user_id)
                
                # Notify referrer
                referrer_message = (
                    f"🎉 <b>Commission Earned!</b> 🎉\n\n"
                    f"One of your referrals has made a payment of {amount:.3f} SOL.\n"
                    f"You earned {commission_amount:.3f} SOL commission!"
                )
                send_message(referrer_id, referrer_message)
            
            # Send confirmation to user with new format
            user_message = (
                f"🎉 <b>Payment Confirmed!</b> 🎉\n\n"
                f"We have received your payment of {amount:.3f} solana\n\n"
                f"Enter /start to begin accessing Translucent's features"
            )
            send_message(user_id, user_message)
        else:
            # User has made a payment but not enough for premium yet
            remaining = max(0, REQUIRED_PAYMENT - user['paid_amount'])
            
            user_message = (
                f"🎉 <b>Payment Confirmed!</b> 🎉\n\n"
                f"We have received your payment of {amount:.3f} solana\n\n"
                f"Enter /start to begin accessing Translucent's features"
            )
            send_message(user_id, user_message)
        
        return True
    except Exception as e:
        logger.error(f"Error handling payment confirmation: {e}", exc_info=True)
        return False

# --- Routes ---

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """Handle webhook requests from Telegram"""
    try:
        update = request.json
        
        # Handle messages
        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            username = message.get('from', {}).get('username')
            
            # Handle commands
            if 'text' in message:
                text = message['text']
                
                if text.startswith('/start'):
                    # Extract start parameter if any
                    parts = text.split()
                    start_param = parts[1] if len(parts) > 1 else None
                    
                    # Special case for web_auth parameter
                    if start_param == 'web_auth':
                        # Generate auth token and send link with button
                        auth_token = db.generate_auth_token(user_id, AUTH_TOKEN_EXPIRY)
                        if auth_token:
                            auth_url = f"{WEBHOOK_HOST}?token={auth_token['token']}"
                            keyboard = {
                                'inline_keyboard': [
                                    [{'text': '🌐 Access Website', 'url': auth_url}]
                                ]
                            }
                            send_message(
                                chat_id,
                                f"🔗 <b>Website Authentication</b> 🔗\n\n"
                                f"Click the button below to access the Translucent website with your account:",
                                keyboard
                            )
                        else:
                            send_message(chat_id, "❌ Failed to generate authentication token. Please try again.")
                        return '', 200
                    
                    # Handle regular start command or referral
                    handle_start_command(chat_id, user_id, username, start_param)
                elif text == '/debug_codes' and user_id in ADMIN_IDS:
                    handle_debug_codes(chat_id, user_id)
                elif text == '/debug_schema' and user_id in ADMIN_IDS:
                    handle_debug_schema(chat_id, user_id)
                else:
                    # Check if user is in a state waiting for input
                    state = db.get_user_state(user_id)
                    message_id = message.get('message_id')
                    if state == 'ADD_WALLET':
                        handle_wallet_input(chat_id, user_id, text, message_id)
                    elif state == 'CREATE_REFERRAL':
                        handle_referral_code_input(chat_id, user_id, text, message_id)
                    elif state == 'SET_PAYOUT_WALLET':
                        handle_payout_wallet_input(chat_id, user_id, text, message_id)
                    # Simply ignore other commands - no need to respond
        
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
            elif data == 'remove_wallet':
                handle_remove_wallet(chat_id, message_id, user_id)
            elif data.startswith('remove_wallet_'):
                # Extract the wallet address from the callback data
                wallet_address = data[len('remove_wallet_'):]
                handle_remove_specific_wallet(chat_id, message_id, user_id, wallet_address)
            elif data == 'back_to_start':
                # Get user info
                user = db.get_user(user_id)
                is_premium = user and user['is_premium']
                
                # Show appropriate welcome message based on premium status
                if is_premium:
                    text = (
                        "⭐👁️ <b>Translucent Lifetime Access</b>\n\n"
                        "🎯 The only trading database for finding wallets to track and copy trade across 5 networks\n"
                        "[ SOL, ETH, BASE, TRON, BSC ]\n\n"
                        "🌐 Twitter/X: <a href='https://twitter.com/translucentrade'>@translucentrade</a>\n"
                        "🟢 Trade on all chains via <a href='https://t.me/gmgnaibot?start=i_iuGhO47u'>GMGN.ai</a>\n"
                        "✏️ Contact the developer: <a href='https://x.com/toursoflife'>@toursoflife</a>\n\n"
                        "👁️ To access the website and login, please click the button below. Links expire, and are not intended to be shared for security reasons\n\n"
                        "💰 The referral program is available. Click the button below to setup/manage your referrals\n\n"
                        "Thank you for using Translucent"
                    )
                else:
                    text = (
                        "👁️ <b>Welcome to Translucent</b>\n\n"
                        "🎯 The only trading database for finding wallets to track and copy trade across 5 networks\n"
                        "[ SOL, ETH, BASE, TRON, BSC ]\n\n"
                        "🌐 Twitter/X: <a href='https://twitter.com/translucentrade'>@translucentrade</a>\n"
                        "🟢 Trade on all chains via <a href='https://t.me/gmgnaibot?start=i_iuGhO47u'>GMGN.ai</a>\n"
                        "✏️ Contact the developer: <a href='https://x.com/toursoflife'>@toursoflife</a>\n\n"
                        "👁️ <b>How to access the website</b>\n\n"
                        "We offer lifetime access for 0.5 solana. Link the wallet you are paying from and then click pay now. Web access will be granted automatically\n\n"
                        "💰 The referral program is available to everybody. Visit the referral program by clicking the button below"
                    )
                
                # Create keyboard based on premium status
                keyboard = get_start_keyboard(is_premium)
                
                # Edit the message with the new text and keyboard
                edit_message(chat_id, message_id, text, keyboard)
            elif data == 'pay_now':
                handle_pay_now(chat_id, message_id, user_id)
            elif data == 'check_payment':
                handle_check_payment(chat_id, message_id, user_id)
            elif data == 'referral_menu':
                handle_referral_menu(chat_id, message_id, user_id)
            elif data == 'create_referral':
                handle_create_referral(chat_id, message_id, user_id)
            elif data == 'change_payout_wallet':
                handle_change_payout_wallet(chat_id, message_id, user_id)
            elif data == 'view_detailed_stats':
                handle_view_detailed_stats(chat_id, message_id, user_id)
            elif data == 'access_website':
                handle_access_website(chat_id, message_id, user_id)
            elif data == 'website_login':
                handle_website_login(chat_id, message_id, user_id)
        
        return '', 200
    except Exception as e:
        logger.error(f"Error processing Telegram update: {e}", exc_info=True)
        return '', 500

@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    """Handle payment webhook from Solana payment processor"""
    try:
        data = request.json
        logger.info(f"Received webhook data: {json.dumps(data, indent=2)}")
        
        # Check if data is a list (multiple transactions)
        if isinstance(data, list):
            logger.info(f"Processing {len(data)} transactions")
            for transaction in data:
                process_transaction(transaction)
        else:
            # Single transaction
            logger.info("Processing single transaction")
            process_transaction(data)
            
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/verify_token_direct', methods=['GET'])
def verify_token_direct():
    """Verify an authentication token directly"""
    token = request.args.get('token')
    if not token:
        return jsonify({'valid': False, 'error': 'No token provided'}), 400
        
    # Verify the token
    user = db.verify_auth_token(token)
    if user:
        return jsonify({
            'valid': True,
            'user': {
                'id': user['telegram_id'],
                'username': user['username'],
                'is_premium': user['is_premium']
            }
        })
    else:
        return jsonify({'valid': False, 'error': 'Invalid or expired token'}), 401

@app.route('/ping', methods=['GET'])
def ping():
    """Simple ping endpoint to check if server is running"""
    return jsonify({'status': 'ok', 'message': 'Server is running'})

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    """Serve the appropriate React app based on authentication"""
    # Skip API endpoints
    if path.startswith('telegram_webhook') or path.startswith('payment_webhook') or path.startswith('verify_token') or path.startswith('api/'):
        return "Not found", 404
    
    # Log the requested path
    logger.info(f"Serving React path: {path}")
    
    # Check if user is authenticated and premium by looking for JWT in Authorization header
    is_premium = False
    auth_header = request.headers.get('Authorization')
    
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            # Decode and verify JWT
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            user = db.get_user(payload['telegram_id'])
            is_premium = user and user['is_premium']
        except:
            # Token invalid or expired, user is not authenticated
            is_premium = False
    
    # Determine which React app to serve
    build_dir = PREMIUM_PAGE_BUILD_DIR if is_premium or path.startswith('premium/') else LANDING_PAGE_BUILD_DIR
    
    # If explicitly requesting premium content but not premium user, redirect to landing
    if path.startswith('premium/') and not is_premium:
        return redirect('/')
    
    # If path starts with 'premium/' and user is premium, strip 'premium/' prefix
    if path.startswith('premium/') and is_premium:
        path = path[8:]  # Remove 'premium/' prefix
    
    # Special case for static files
    if path.startswith('static/'):
        # Extract the file path relative to the build directory
        file_path = path
        directory = os.path.join(build_dir, os.path.dirname(file_path))
        filename = os.path.basename(file_path)
        logger.info(f"Serving static file: {filename} from {directory}")
        return send_from_directory(directory, filename)
    
    # Check if the file exists in the build directory
    if path and os.path.exists(os.path.join(build_dir, path)):
        logger.info(f"Serving file: {path} from {build_dir}")
        return send_from_directory(build_dir, path)
    
    # For all other routes, serve the index.html from the appropriate build directory
    logger.info(f"Serving index.html from {build_dir}")
    if os.path.exists(os.path.join(build_dir, 'index.html')):
        return send_from_directory(build_dir, 'index.html')
    else:
        logger.error(f"index.html not found in {build_dir}")
        return "React app not built. Run 'npm run build' in the appropriate React app directory.", 500

# Add a route to serve premium static files separately
@app.route('/premium/static/<path:path>')
def serve_premium_static(path):
    """Serve static files from the premium React build directory"""
    logger.info(f"Serving premium static file: {path}")
    return send_from_directory(os.path.join(PREMIUM_PAGE_BUILD_DIR, 'static'), path)

# The regular static route remains for landing page
@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files from the landing page React build directory"""
    logger.info(f"Serving landing page static file: {path}")
    return send_from_directory(os.path.join(LANDING_PAGE_BUILD_DIR, 'static'), path)

if __name__ == '__main__':
    # Add any missing columns to the database
    db.add_missing_columns()
    
    # Set the webhook from config
    webhook_url = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    set_webhook_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    
    logger.info(f"Setting webhook to {webhook_url}")
    response = requests.get(set_webhook_url)
    logger.info(f"Webhook set response: {response.json()}")
    
    # Run the Flask app
    logger.info(f"Starting combined webhook server on port {PORT}")
    app.run(host='0.0.0.0', port=PORT) 