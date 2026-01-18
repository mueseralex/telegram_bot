import requests
import time
import json
import logging
from config import BOT_TOKEN, DATABASE_PATH
from database import Database
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters, MessageHandler

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}/"
        self.offset = 0
        self.db = Database(DATABASE_PATH)
        
    def get_updates(self):
        """Get updates from Telegram API"""
        params = {
            'offset': self.offset,
            'timeout': 30,
            'allowed_updates': ['message', 'callback_query']
        }
        response = requests.get(self.api_url + 'getUpdates', params=params)
        return response.json()
    
    def send_message(self, chat_id, text, reply_markup=None):
        """Send message to user"""
        params = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        if reply_markup:
            params['reply_markup'] = json.dumps(reply_markup)
            
        response = requests.post(self.api_url + 'sendMessage', params=params)
        return response.json()
    
    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        """Edit message text"""
        params = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        if reply_markup:
            params['reply_markup'] = json.dumps(reply_markup)
            
        response = requests.post(self.api_url + 'editMessageText', params=params)
        return response.json()
    
    def handle_message(self, message):
        """Handle incoming message"""
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        
        # Store user in database if not exists
        username = message['from'].get('username', '')
        self.db.add_user_if_not_exists(user_id, username)
        
        # Handle commands
        if 'text' in message:
            text = message['text']
            
            if text.startswith('/start'):
                self.handle_start_command(chat_id, user_id)
            elif text.startswith('/myid'):
                self.handle_myid_command(chat_id, user_id)
            elif text.startswith('/referral'):
                self.handle_referral_command(chat_id, user_id)
            elif text.startswith('/admin_stats') and self.is_admin(user_id):
                self.handle_admin_stats_command(chat_id, user_id)
            elif text.startswith('/whitelist') and self.is_admin(user_id):
                self.handle_whitelist_command(chat_id, user_id, text)
            else:
                # Handle wallet address input
                self.handle_text_input(chat_id, user_id, text)
    
    def handle_callback_query(self, callback_query):
        """Handle callback query from inline keyboards"""
        query_id = callback_query['id']
        chat_id = callback_query['message']['chat']['id']
        message_id = callback_query['message']['message_id']
        user_id = callback_query['from']['id']
        data = callback_query['data']
        
        # Answer callback query to stop loading animation
        requests.post(self.api_url + 'answerCallbackQuery', {'callback_query_id': query_id})
        
        # Handle different callback data
        if data == 'wallet_menu':
            self.handle_wallet_menu(chat_id, message_id, user_id)
        elif data == 'add_wallet':
            self.handle_add_wallet(chat_id, message_id, user_id)
        elif data == 'back_to_start':
            self.handle_start_command(chat_id, user_id, message_id)
        elif data == 'pay_now':
            self.handle_pay_now(chat_id, message_id, user_id)
        elif data == 'check_payment':
            self.handle_check_payment(chat_id, message_id, user_id)
        elif data == 'referral_menu':
            self.handle_referral_menu(chat_id, message_id, user_id)
    
    def handle_start_command(self, chat_id, user_id, message_id=None):
        """Handle /start command"""
        user = self.db.get_user(user_id)
        is_premium = user and user['is_premium']
        
        if is_premium:
            text = (
                "🌟 <b>Welcome to Translucent Premium!</b> 🌟\n\n"
                "You have full access to all premium features."
            )
        else:
            text = (
                "👋 <b>Welcome to Translucent!</b>\n\n"
                "To access premium features, please link your wallet and make a payment."
            )
        
        # Create keyboard
        keyboard = self.get_start_keyboard(is_premium)
        
        if message_id:
            self.edit_message_text(chat_id, message_id, text, keyboard)
        else:
            self.send_message(chat_id, text, keyboard)
    
    def handle_myid_command(self, chat_id, user_id):
        """Handle /myid command"""
        user = self.db.get_user(user_id)
        username = user['username'] if user else 'None'
        
        text = (
            f"Your Telegram Information:\n\n"
            f"ID: {user_id}\n"
            f"Username: @{username}"
        )
        
        self.send_message(chat_id, text)
    
    def handle_wallet_menu(self, chat_id, message_id, user_id):
        """Handle wallet menu button click"""
        wallets = self.db.get_user_wallets(user_id)
        
        text = "💰 <b>Wallet Management</b> 💰\n\n"
        
        if wallets:
            text += "Your linked wallets:\n\n"
            for i, wallet in enumerate(wallets, 1):
                address = wallet['solana_address']
                text += f"{i}. <code>{address[:6]}...{address[-4:]}</code>\n"
        else:
            text += "You don't have any wallets linked yet. Add a wallet to continue."
        
        keyboard = self.get_wallet_management_keyboard(wallets)
        
        self.edit_message_text(chat_id, message_id, text, keyboard)
    
    def handle_add_wallet(self, chat_id, message_id, user_id):
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
        
        self.edit_message_text(chat_id, message_id, text, keyboard)
        
        # Store state in database
        self.db.set_user_state(user_id, 'ADD_WALLET')
    
    def handle_text_input(self, chat_id, user_id, text):
        """Handle text input based on user state"""
        state = self.db.get_user_state(user_id)
        
        if state == 'ADD_WALLET':
            # Validate wallet address
            if self.validate_solana_address(text):
                # Add wallet to database
                self.db.add_wallet(user_id, text)
                
                # Reset state
                self.db.set_user_state(user_id, None)
                
                # Send confirmation
                message = (
                    f"✅ Wallet added successfully!\n\n"
                    f"Address: <code>{text[:6]}...{text[-4:]}</code>"
                )
                
                keyboard = self.get_wallet_management_keyboard(self.db.get_user_wallets(user_id))
                
                self.send_message(chat_id, message, keyboard)
            else:
                self.send_message(
                    chat_id, 
                    "❌ Invalid Solana address. Please try again with a valid address."
                )
    
    def handle_pay_now(self, chat_id, message_id, user_id):
        """Handle pay now button click"""
        from config import DEPOSIT_ADDRESS, REQUIRED_PAYMENT
        
        text = (
            f"💸 <b>Payment Information</b> 💸\n\n"
            f"Please send <b>{REQUIRED_PAYMENT} SOL</b> to the following address:\n\n"
            f"<code>{DEPOSIT_ADDRESS}</code>\n\n"
            f"Once your payment is confirmed, you'll automatically get premium access."
        )
        
        keyboard = {
            'inline_keyboard': [
                [{'text': '🔙 Back', 'callback_data': 'wallet_menu'}]
            ]
        }
        
        self.edit_message_text(chat_id, message_id, text, keyboard)
    
    def handle_referral_command(self, chat_id, user_id):
        """Handle /referral command"""
        referral_code = self.db.get_referral_code(user_id)
        
        if referral_code:
            # User already has a referral code
            stats = self.db.get_referral_stats(user_id)
            
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
        
        keyboard = self.get_referral_keyboard(referral_code is not None)
        
        self.send_message(chat_id, text, keyboard)
    
    def handle_referral_menu(self, chat_id, message_id, user_id):
        """Handle referral menu button click"""
        # Similar to handle_referral_command but edit message instead
        referral_code = self.db.get_referral_code(user_id)
        
        if referral_code:
            # User already has a referral code
            stats = self.db.get_referral_stats(user_id)
            
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
        
        keyboard = self.get_referral_keyboard(referral_code is not None)
        
        self.edit_message_text(chat_id, message_id, text, keyboard)
    
    def handle_admin_stats_command(self, chat_id, user_id):
        """Handle /admin_stats command"""
        if not self.is_admin(user_id):
            self.send_message(chat_id, "⛔ You don't have permission to use this command.")
            return
        
        # Get statistics
        total_users = len(self.db.get_all_users(limit=1000000))
        premium_users = len(self.db.get_premium_users())
        
        # Get total payments
        payments = self.db.get_all_payments()
        total_payments = sum(p['amount'] for p in payments)
        
        # Get referral stats
        referrals = self.db.get_all_referrals()
        total_referrals = len(referrals)
        converted_referrals = sum(1 for r in referrals if r['converted'])
        total_commission = sum(r['commission_owed'] for r in referrals if r['converted'])
        
        # Calculate conversion rates safely
        user_conversion_rate = (premium_users/total_users*100) if total_users > 0 else 0
        referral_conversion_rate = (converted_referrals/total_referrals*100) if total_referrals > 0 else 0
        
        text = (
            f"📊 <b>Admin Statistics</b> 📊\n\n"
            f"Users:\n"
            f"• Total users: {total_users}\n"
            f"• Premium users: {premium_users}\n"
            f"• Conversion rate: {user_conversion_rate:.1f}%\n\n"
            f"Payments:\n"
            f"• Total payments: {len(payments)}\n"
            f"• Total amount: {total_payments:.2f} SOL\n\n"
            f"Referrals:\n"
            f"• Total referrals: {total_referrals}\n"
            f"• Converted referrals: {converted_referrals}\n"
            f"• Conversion rate: {referral_conversion_rate:.1f}%\n"
            f"• Total commission owed: {total_commission:.2f} SOL"
        )
        
        self.send_message(chat_id, text)
    
    def handle_whitelist_command(self, chat_id, user_id, text):
        """Handle /whitelist command"""
        if not self.is_admin(user_id):
            self.send_message(chat_id, "⛔ You don't have permission to use this command.")
            return
        
        # Parse command arguments
        parts = text.split()
        if len(parts) < 2:
            self.send_message(
                chat_id,
                "Please provide a username or Telegram ID to whitelist.\n\n"
                "Usage: /whitelist username OR /whitelist 123456789"
            )
            return
        
        identifier = parts[1]
        
        # Check if input is a numeric ID
        if identifier.isdigit():
            target_id = int(identifier)
            user = self.db.get_user(target_id)
            
            if not user:
                self.send_message(chat_id, f"User with ID {target_id} not found in database.")
                return
                
            # Set user to premium
            self.db.set_premium_status(target_id, True)
            self.send_message(chat_id, f"✅ User with ID {target_id} has been granted premium access.")
            
        # Otherwise treat as username
        else:
            # If username starts with @, remove it
            if identifier.startswith('@'):
                identifier = identifier[1:]
            
            # Find user by username
            user = self.db.get_user_by_username(identifier)
            
            if not user:
                self.send_message(chat_id, f"User with username '{identifier}' not found in database.")
                return
                
            # Set user to premium
            self.db.set_premium_status(user['telegram_id'], True)
            self.send_message(chat_id, f"✅ User @{identifier} has been granted premium access.")
    
    def is_admin(self, user_id):
        """Check if user is an admin"""
        from config import ADMIN_IDS
        return user_id in ADMIN_IDS
    
    def validate_solana_address(self, address):
        """Basic validation for Solana addresses"""
        import re
        # Solana addresses are base58 encoded and typically 32-44 characters
        return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))
    
    def get_start_keyboard(self, is_premium=False):
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
    
    def get_wallet_management_keyboard(self, wallets=None):
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
    
    def get_referral_keyboard(self, has_referral=False):
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
    
    def run(self):
        """Run the bot"""
        logger.info("Starting bot...")
        
        while True:
            try:
                updates = self.get_updates()
                
                if 'result' in updates:
                    for update in updates['result']:
                        # Update offset to acknowledge updates
                        self.offset = update['update_id'] + 1
                        
                        # Handle message
                        if 'message' in update:
                            self.handle_message(update['message'])
                        
                        # Handle callback query
                        elif 'callback_query' in update:
                            self.handle_callback_query(update['callback_query'])
                
                # Sleep to avoid hitting rate limits
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(5)

def main():
    """Main function"""
    bot = TelegramBot(BOT_TOKEN)
    bot.run()

if __name__ == '__main__':
    main() 