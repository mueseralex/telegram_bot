from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
import re

# Import keyboards
from keyboards.referral_keyboards import get_referral_keyboard, get_referral_stats_keyboard

# States for conversation handler
REFERRAL_MENU, CREATE_REFERRAL, ENTER_USERNAME, CONNECT_PAYOUT_WALLET = range(4)

def referral_command(update: Update, context: CallbackContext):
    """Handle the /referral command"""
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Check if user already has a referral code
    referral_code = db.get_referral_code(user_id)
    
    if referral_code:
        # User already has a referral code, show stats
        stats = db.get_referral_stats(user_id)
        
        update.message.reply_text(
            f"🔄 Your Referral Link 🔄\n\n"
            f"🔗 t.me/{context.bot.username}?start={referral_code['referral_username']}\n\n"
            f"Payout Wallet: {referral_code['payout_wallet'][:5]}...{referral_code['payout_wallet'][-4:] if referral_code['payout_wallet'] else 'Not set'}\n\n"
            f"Referral Stats:\n"
            f"• Total referrals: {stats['total']}\n"
            f"• Successful conversions: {stats['converted']}\n"
            f"• Commission earned: {stats['total_commission']} SOL (not yet paid)",
            reply_markup=get_referral_stats_keyboard()
        )
    else:
        # User doesn't have a referral code yet
        update.message.reply_text(
            f"🔄 Referral Program 🔄\n\n"
            f"Invite friends to join Translucent and earn rewards!\n\n"
            f"For each friend who purchases lifetime access through your referral link, "
            f"you'll earn 5% commission on their payment (0.025 SOL per referral).\n\n"
            f"Ready to create your personal referral link?",
            reply_markup=get_referral_keyboard()
        )
    
    return ConversationHandler.END

def referral_menu_callback(update: Update, context: CallbackContext):
    """Handle referral menu button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Check if user already has a referral code
    referral_code = db.get_referral_code(user_id)
    
    if referral_code:
        # User already has a referral code, show stats
        stats = db.get_referral_stats(user_id)
        
        query.edit_message_text(
            f"🔄 Your Referral Link 🔄\n\n"
            f"🔗 t.me/{context.bot.username}?start={referral_code['referral_username']}\n\n"
            f"Payout Wallet: {referral_code['payout_wallet'][:5]}...{referral_code['payout_wallet'][-4:] if referral_code['payout_wallet'] else 'Not set'}\n\n"
            f"Referral Stats:\n"
            f"• Total referrals: {stats['total']}\n"
            f"• Successful conversions: {stats['converted']}\n"
            f"• Commission earned: {stats['total_commission']} SOL (not yet paid)",
            reply_markup=get_referral_stats_keyboard()
        )
        return REFERRAL_MENU
    else:
        # User doesn't have a referral code yet
        query.edit_message_text(
            f"🔄 Referral Program 🔄\n\n"
            f"Invite friends to join Translucent and earn rewards!\n\n"
            f"For each friend who purchases lifetime access through your referral link, "
            f"you'll earn 5% commission on their payment (0.025 SOL per referral).\n\n"
            f"Ready to create your personal referral link?",
            reply_markup=get_referral_keyboard()
        )
        return REFERRAL_MENU

def create_referral_callback(update: Update, context: CallbackContext):
    """Handle create referral button click"""
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        "Please enter a username for your referral link.\n\n"
        "Requirements:\n"
        "• 3-15 characters\n"
        "• Letters, numbers, and underscores only\n"
        "• Must be unique\n\n"
        "This will create a link like: t.me/TranslucentBot?start=username",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
        ]])
    )
    
    return ENTER_USERNAME

def process_referral_username(update: Update, context: CallbackContext):
    """Process the referral username sent by the user"""
    user_id = update.effective_user.id
    username = update.message.text.strip()
    db = context.dispatcher.bot_data['db']
    
    # Validate username
    if len(username) < 3 or len(username) > 15:
        update.message.reply_text(
            "❌ Username must be between 3 and 15 characters.\n\n"
            "Please try again with a different username.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
            ]])
        )
        return ENTER_USERNAME
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        update.message.reply_text(
            "❌ Username can only contain letters, numbers, and underscores.\n\n"
            "Please try again with a different username.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
            ]])
        )
        return ENTER_USERNAME
    
    # Check if username is reserved
    reserved_words = ["admin", "help", "start", "settings", "premium", "pay"]
    if username.lower() in reserved_words:
        update.message.reply_text(
            "❌ This username is reserved and cannot be used.\n\n"
            "Please try again with a different username.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
            ]])
        )
        return ENTER_USERNAME
    
    # Store username temporarily
    context.user_data['referral_username'] = username
    
    # Check if username is available
    existing_user = db.get_user_by_referral_code(username)
    if existing_user and existing_user != user_id:
        update.message.reply_text(
            f"❌ The username '{username}' is already taken.\n\n"
            f"Please try again with a different username.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
            ]])
        )
        return ENTER_USERNAME
    
    # Username is valid, ask for payout wallet
    update.message.reply_text(
        f"✅ Your referral link has been created!\n\n"
        f"🔗 t.me/{update.effective_chat.bot.username}?start={username}\n\n"
        f"Now, please connect a wallet to receive your referral commissions:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 Connect Payout Wallet", callback_data="connect_payout_wallet")
        ]])
    )
    
    return REFERRAL_MENU

def connect_payout_wallet_callback(update: Update, context: CallbackContext):
    """Handle connect payout wallet button click"""
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        "Please send your Solana wallet address where you'd like to receive referral commissions.\n\n"
        "This wallet will be used for all future payouts. You can change it later if needed.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
        ]])
    )
    
    return CONNECT_PAYOUT_WALLET

def process_payout_wallet(update: Update, context: CallbackContext):
    """Process the payout wallet address sent by the user"""
    user_id = update.effective_user.id
    wallet_address = update.message.text.strip()
    db = context.dispatcher.bot_data['db']
    
    # Validate Solana address (basic check)
    if not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', wallet_address):
        update.message.reply_text(
            "❌ Invalid Solana address format.\n\n"
            "Please send a valid Solana wallet address, or click Back to cancel.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
            ]])
        )
        return CONNECT_PAYOUT_WALLET
    
    # Get referral username from user_data
    referral_username = context.user_data.get('referral_username')
    
    # Create or update referral code
    success, message = db.create_referral_code(user_id, referral_username, wallet_address)
    
    if success:
        # Get referral stats
        stats = db.get_referral_stats(user_id)
        
        update.message.reply_text(
            f"✅ Payout wallet connected successfully!\n\n"
            f"Address: {wallet_address[:5]}...{wallet_address[-4:]}\n\n"
            f"Share your referral link with friends. When they purchase lifetime access to Translucent, you'll earn 5% commission!\n\n"
            f"Current Stats:\n"
            f"• Total referrals: {stats['total']}\n"
            f"• Successful conversions: {stats['converted']}\n"
            f"• Commission earned: {stats['total_commission']} SOL\n\n"
            f"Use /referral anytime to view your stats and link.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")
            ]])
        )
        return ConversationHandler.END
    else:
        update.message.reply_text(
            f"❌ {message}\n\n"
            f"Please try again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
            ]])
        )
        return CONNECT_PAYOUT_WALLET

def change_payout_wallet_callback(update: Update, context: CallbackContext):
    """Handle change payout wallet button click"""
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        "Please send your new Solana wallet address where you'd like to receive referral commissions.\n\n"
        "This wallet will be used for all future payouts.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
        ]])
    )
    
    return CONNECT_PAYOUT_WALLET

def view_detailed_stats_callback(update: Update, context: CallbackContext):
    """Handle view detailed stats button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get referral code
    referral_code = db.get_referral_code(user_id)
    
    if not referral_code:
        query.edit_message_text(
            "You don't have a referral code yet. Please create one first.",
            reply_markup=get_referral_keyboard()
        )
        return REFERRAL_MENU
    
    # Get detailed stats
    stats = db.get_referral_stats(user_id)
    
    # Format referrals list
    referrals_text = ""
    for i, ref in enumerate(stats['referrals'][:10]):  # Show only first 10 referrals
        username = ref['referee_username'] or f"User{ref['referee_id']}"
        converted = "Yes" if ref['converted'] else "No"
        commission = f"{ref['commission_owed']} SOL" if ref['converted'] else "N/A"
        
        referrals_text += f"{i+1}. {username} - Joined: {ref['referral_date'][:10]} - Premium: {converted} - Commission: {commission}\n"
    
    if not referrals_text:
        referrals_text = "No referrals yet."
    
    query.edit_message_text(
        f"📊 Detailed Referral Stats 📊\n\n"
        f"Your referral link: t.me/{context.bot.username}?start={referral_code['referral_username']}\n\n"
        f"Referrals:\n{referrals_text}\n\n"
        f"Total Commission: {stats['total_commission']} SOL (not yet paid)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Change Username", callback_data="change_username")],
            [InlineKeyboardButton("Change Payout Wallet", callback_data="change_payout_wallet")],
            [InlineKeyboardButton("🔙 Back", callback_data="referral_menu")]
        ])
    )
    
    return REFERRAL_MENU

def change_username_callback(update: Update, context: CallbackContext):
    """Handle change username button click"""
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        "Please enter a new username for your referral link.\n\n"
        "Requirements:\n"
        "• 3-15 characters\n"
        "• Letters, numbers, and underscores only\n"
        "• Must be unique\n\n"
        "This will create a link like: t.me/TranslucentBot?start=username",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back", callback_data="referral_menu")
        ]])
    )
    
    return ENTER_USERNAME

def back_to_start_callback(update: Update, context: CallbackContext):
    """Handle back to start button click"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    db = context.dispatcher.bot_data['db']
    
    # Get user info
    user = db.get_user(user_id)
    
    # Import start keyboard
    from keyboards.start_keyboards import get_start_keyboard
    
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

# Create conversation handler for referral management
referral_conversation_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(referral_menu_callback, pattern='^referral_menu$'),
    ],
    states={
        REFERRAL_MENU: [
            CallbackQueryHandler(create_referral_callback, pattern='^create_referral$'),
            CallbackQueryHandler(view_detailed_stats_callback, pattern='^view_detailed_stats$'),
            CallbackQueryHandler(change_payout_wallet_callback, pattern='^change_payout_wallet$'),
            CallbackQueryHandler(change_username_callback, pattern='^change_username$'),
            CallbackQueryHandler(back_to_start_callback, pattern='^back_to_start$'),
        ],
        ENTER_USERNAME: [
            MessageHandler(Filters.text & ~Filters.command, process_referral_username),
            CallbackQueryHandler(referral_menu_callback, pattern='^referral_menu$'),
        ],
        CONNECT_PAYOUT_WALLET: [
            MessageHandler(Filters.text & ~Filters.command, process_payout_wallet),
            CallbackQueryHandler(referral_menu_callback, pattern='^referral_menu$'),
        ],
    },
    fallbacks=[CommandHandler('referral', referral_command)],
) 