from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
import re

# Import keyboards
from keyboards.start_keyboards import get_start_keyboard, get_wallet_management_keyboard, get_remove_wallet_keyboard, get_confirm_remove_keyboard

# States for conversation handler
WALLET_MENU, ADD_WALLET, REMOVE_WALLET, CONFIRM_REMOVE = range(4)

def start_command(update: Update, context: CallbackContext):
    """Handle the /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    db = context.dispatcher.bot_data['db']
    
    # Add user to database if they don't exist
    if not db.user_exists(user_id):
        db.add_user(user_id, username)
        
    # Check if user came from a referral link
    args = context.args
    if args and len(args) > 0:
        referral_username = args[0]
        referrer_id = db.get_user_by_referral_code(referral_username)
        
        if referrer_id and referrer_id != user_id:  # Prevent self-referrals
            db.record_referral(referrer_id, user_id)
            update.message.reply_text(f"Welcome! You were invited by a friend.")
    
    # Get user info
    user = db.get_user(user_id)
    
    # Check if user is premium
    if user and user['is_premium']:
        # User is premium, show premium welcome
        wallets = db.get_wallets(user_id)
        wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:5]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
        
        update.message.reply_text(
            f"👋 Welcome back!\n\n"
            f"✅ You have lifetime access to Translucent.\n\n"
            f"Payment Details:\n"
            f"• Amount Paid: {user['paid_amount']} SOL\n"
            f"• Payment Date: {user['last_payment_date']}\n\n"
            f"Your Linked Wallets:\n{wallet_text}",
            reply_markup=get_start_keyboard(is_premium=True)
        )
    else:
        # User is not premium, show regular welcome
        update.message.reply_text(
            f"👋 Welcome to Translucent Bot!\n\n"
            f"Get lifetime access to Translucent by making a one-time payment of 0.5 SOL.\n\n"
            f"What would you like to do?",
            reply_markup=get_start_keyboard(is_premium=False)
        )
    
    return ConversationHandler.END

def wallet_menu_callback(update: Update, context: CallbackContext):
    """Handle wallet menu button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user's wallets
    wallets = db.get_wallets(user_id)
    
    if wallets:
        wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:5]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
        query.edit_message_text(
            f"Your Linked Wallets:\n{wallet_text}\n\nWhat would you like to do?",
            reply_markup=get_wallet_management_keyboard(wallets)
        )
    else:
        query.edit_message_text(
            "You don't have any wallets linked yet.\n\nPlease add a wallet to continue.",
            reply_markup=get_wallet_management_keyboard()
        )
    
    return WALLET_MENU

def add_wallet_callback(update: Update, context: CallbackContext):
    """Handle add wallet button click"""
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        "Please send your Solana wallet address to link it to your account.\n\n"
        "Your wallet address should look like: 5WvztoHrHhJmxWwnJGT3Kh9cZxSDbuHqVowDHEStQ55j\n\n"
        "Send the address as text, or click Back to cancel.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="back_to_wallet_menu")
        ]])
    )
    
    return ADD_WALLET

def process_add_wallet(update: Update, context: CallbackContext):
    """Process the wallet address sent by the user"""
    user_id = update.effective_user.id
    wallet_address = update.message.text.strip()
    db = context.dispatcher.bot_data['db']
    
    # Validate Solana address (basic check)
    if not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', wallet_address):
        update.message.reply_text(
            "❌ Invalid Solana address format.\n\n"
            "Please send a valid Solana wallet address, or click Back to cancel.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_to_wallet_menu")
            ]])
        )
        return ADD_WALLET
    
    # Add wallet to database
    success, message = db.add_wallet(user_id, wallet_address)
    
    if success:
        # Get updated wallet list
        wallets = db.get_wallets(user_id)
        wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:5]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
        
        update.message.reply_text(
            f"✅ Wallet successfully linked!\n\n"
            f"Address: {wallet_address[:5]}...{wallet_address[-4:]}\n\n"
            f"Your Linked Wallets:\n{wallet_text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Pay Now", callback_data="pay_now")],
                [InlineKeyboardButton("🔙 Back to Wallet Menu", callback_data="wallet_menu")]
            ])
        )
        return ConversationHandler.END
    else:
        update.message.reply_text(
            f"❌ {message}\n\n"
            f"Please try again with a different address, or click Back to cancel.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_to_wallet_menu")
            ]])
        )
        return ADD_WALLET

def remove_wallet_callback(update: Update, context: CallbackContext):
    """Handle remove wallet button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user's wallets
    wallets = db.get_wallets(user_id)
    
    if not wallets:
        query.edit_message_text(
            "You don't have any wallets to remove.",
            reply_markup=get_wallet_management_keyboard()
        )
        return WALLET_MENU
    
    query.edit_message_text(
        "Select a wallet to remove:",
        reply_markup=get_remove_wallet_keyboard(wallets)
    )
    
    return REMOVE_WALLET

def confirm_remove_wallet_callback(update: Update, context: CallbackContext):
    """Handle wallet selection for removal"""
    query = update.callback_query
    query.answer()
    
    # Extract wallet ID from callback data
    wallet_id = int(query.data.split('_')[-1])
    context.user_data['wallet_to_remove'] = wallet_id
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get wallet details
    wallets = db.get_wallets(user_id)
    wallet = next((w for w in wallets if w['id'] == wallet_id), None)
    
    if not wallet:
        query.edit_message_text(
            "Wallet not found. Please try again.",
            reply_markup=get_wallet_management_keyboard(wallets)
        )
        return WALLET_MENU
    
    address = wallet['solana_address']
    short_address = f"{address[:5]}...{address[-4:]}"
    
    query.edit_message_text(
        f"Are you sure you want to remove this wallet?\n\n"
        f"Address: {short_address}\n\n"
        f"Note: Your payment history will be preserved.",
        reply_markup=get_confirm_remove_keyboard(wallet_id)
    )
    
    return CONFIRM_REMOVE

def do_remove_wallet_callback(update: Update, context: CallbackContext):
    """Handle wallet removal confirmation"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    wallet_id = int(query.data.split('_')[-1])
    db = context.dispatcher.bot_data['db']
    
    # Remove wallet
    success = db.remove_wallet(user_id, wallet_id)
    
    # Get updated wallet list
    wallets = db.get_wallets(user_id)
    
    if success:
        if wallets:
            wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:5]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
            query.edit_message_text(
                f"✅ Wallet removed successfully.\n\n"
                f"Your Linked Wallets:\n{wallet_text}",
                reply_markup=get_wallet_management_keyboard(wallets)
            )
        else:
            query.edit_message_text(
                "✅ Wallet removed successfully.\n\n"
                "You don't have any wallets linked. Please add a wallet to continue.",
                reply_markup=get_wallet_management_keyboard()
            )
    else:
        query.edit_message_text(
            "❌ Failed to remove wallet. Please try again.",
            reply_markup=get_wallet_management_keyboard(wallets)
        )
    
    return WALLET_MENU

def back_to_wallet_menu_callback(update: Update, context: CallbackContext):
    """Handle back to wallet menu button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user's wallets
    wallets = db.get_wallets(user_id)
    
    if wallets:
        wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:5]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
        query.edit_message_text(
            f"Your Linked Wallets:\n{wallet_text}\n\nWhat would you like to do?",
            reply_markup=get_wallet_management_keyboard(wallets)
        )
    else:
        query.edit_message_text(
            "You don't have any wallets linked yet.\n\nPlease add a wallet to continue.",
            reply_markup=get_wallet_management_keyboard()
        )
    
    return WALLET_MENU

def back_to_remove_wallet_callback(update: Update, context: CallbackContext):
    """Handle cancel remove button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user's wallets
    wallets = db.get_wallets(user_id)
    
    query.edit_message_text(
        "Select a wallet to remove:",
        reply_markup=get_remove_wallet_keyboard(wallets)
    )
    
    return REMOVE_WALLET

def back_to_start_callback(update: Update, context: CallbackContext):
    """Handle back to start button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user info
    user = db.get_user(user_id)
    
    # Check if user is premium
    if user and user['is_premium']:
        # User is premium, show premium welcome
        wallets = db.get_wallets(user_id)
        wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:5]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
        
        query.edit_message_text(
            f"👋 Welcome back!\n\n"
            f"✅ You have lifetime access to Translucent.\n\n"
            f"Payment Details:\n"
            f"• Amount Paid: {user['paid_amount']} SOL\n"
            f"• Payment Date: {user['last_payment_date']}\n\n"
            f"Your Linked Wallets:\n{wallet_text}",
            reply_markup=get_start_keyboard(is_premium=True)
        )
    else:
        # User is not premium, show regular welcome
        query.edit_message_text(
            f"👋 Welcome to Translucent Bot!\n\n"
            f"Get lifetime access to Translucent by making a one-time payment of 0.5 SOL.\n\n"
            f"What would you like to do?",
            reply_markup=get_start_keyboard(is_premium=False)
        )
    
    return ConversationHandler.END

def pay_now_callback(update: Update, context: CallbackContext):
    """Handle pay now button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user's wallets
    wallets = db.get_wallets(user_id)
    
    if not wallets:
        query.edit_message_text(
            "⚠️ You need to link a wallet before making a payment.\n\n"
            "Please link your Solana wallet first, then you can proceed with payment.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔗 Link Wallet", callback_data="wallet_menu")
            ]])
        )
        return ConversationHandler.END
    
    from config import DEPOSIT_ADDRESS, REQUIRED_PAYMENT
    
    wallet_text = "\n".join([f"{i+1}. {w['solana_address'][:5]}...{w['solana_address'][-4:]}" for i, w in enumerate(wallets)])
    
    query.edit_message_text(
        f"💰 Payment Instructions\n\n"
        f"Please send {REQUIRED_PAYMENT} SOL from one of your linked wallets to:\n\n"
        f"Address: {DEPOSIT_ADDRESS}\n\n"
        f"Important:\n"
        f"• Send exactly {REQUIRED_PAYMENT} SOL\n"
        f"• This is a one-time payment for lifetime access to Translucent\n"
        f"• Only send from your linked wallets\n"
        f"• Payment will be automatically detected\n\n"
        f"Your Linked Wallets:\n{wallet_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Check Payment Status", callback_data="check_payment")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_start")]
        ])
    )
    
    return ConversationHandler.END

def check_payment_callback(update: Update, context: CallbackContext):
    """Handle check payment status button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user info
    user = db.get_user(user_id)
    
    if user and user['is_premium']:
        # User is premium
        payments = db.get_payment_history(user_id)
        latest_payment = payments[0] if payments else None
        
        if latest_payment:
            query.edit_message_text(
                f"✅ Payment received!\n\n"
                f"Amount: {latest_payment['amount']} SOL\n"
                f"From: {latest_payment['solana_address'][:5]}...{latest_payment['solana_address'][-4:]}\n"
                f"Transaction ID: {latest_payment['transaction_id'][:5]}...{latest_payment['transaction_id'][-4:]}\n"
                f"Date: {latest_payment['payment_date']}\n\n"
                f"You now have lifetime access to Translucent! Thank you for your payment.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")
                ]])
            )
        else:
            query.edit_message_text(
                f"✅ You have premium access to Translucent.\n\n"
                f"No payment details found in the database.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")
                ]])
            )
    else:
        # User is not premium
        from config import REQUIRED_PAYMENT
        remaining = REQUIRED_PAYMENT - (user['paid_amount'] if user else 0)
        
        query.edit_message_text(
            f"🔄 Checking payment status...\n\n"
            f"❌ No payment detected yet.\n\n"
            f"Please send {remaining} SOL to complete your payment.\n\n"
            f"If you've already sent the payment, please wait a few minutes for it to be processed.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Again", callback_data="check_payment")],
                [InlineKeyboardButton("🔙 Back to Payment Instructions", callback_data="pay_now")]
            ])
        )
    
    return ConversationHandler.END

def my_id_command(update: Update, context: CallbackContext):
    """Show the user their Telegram ID"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    update.message.reply_text(
        f"Your Telegram Information:\n\n"
        f"ID: {user_id}\n"
        f"Username: @{username if username else 'None'}"
    )
    
    return ConversationHandler.END

# Create conversation handler for wallet management
wallet_conversation_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(wallet_menu_callback, pattern='^wallet_menu$'),
        CallbackQueryHandler(pay_now_callback, pattern='^pay_now$'),
        CallbackQueryHandler(check_payment_callback, pattern='^check_payment$')
    ],
    states={
        WALLET_MENU: [
            CallbackQueryHandler(add_wallet_callback, pattern='^add_wallet$'),
            CallbackQueryHandler(remove_wallet_callback, pattern='^remove_wallet$'),
            CallbackQueryHandler(back_to_start_callback, pattern='^back_to_start$'),
        ],
        ADD_WALLET: [
            MessageHandler(Filters.text & ~Filters.command, process_add_wallet),
            CallbackQueryHandler(back_to_wallet_menu_callback, pattern='^back_to_wallet_menu$'),
        ],
        REMOVE_WALLET: [
            CallbackQueryHandler(confirm_remove_wallet_callback, pattern='^remove_wallet_id_'),
            CallbackQueryHandler(back_to_wallet_menu_callback, pattern='^back_to_wallet_menu$'),
        ],
        CONFIRM_REMOVE: [
            CallbackQueryHandler(do_remove_wallet_callback, pattern='^confirm_remove_'),
            CallbackQueryHandler(back_to_remove_wallet_callback, pattern='^cancel_remove$'),
        ],
    },
    fallbacks=[CommandHandler('start', start_command)],
) 