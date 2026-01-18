from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
import csv
import io
from datetime import datetime

# Import configuration
from config import ADMIN_IDS

# States for conversation handler
LOOKUP_USER, EXPORT_DATA = range(2)

def is_admin(user_id):
    """Check if user is an admin"""
    return user_id in ADMIN_IDS

def admin_required(func):
    """Decorator to restrict access to admins only"""
    def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            update.message.reply_text("⛔ You don't have permission to use this command.")
            return ConversationHandler.END
        return func(update, context, *args, **kwargs)
    return wrapper

@admin_required
def admin_stats(update: Update, context: CallbackContext):
    """Show admin statistics"""
    db = context.dispatcher.bot_data['db']
    
    # Get statistics
    total_users = len(db.get_all_users(limit=1000000))
    premium_users = len(db.get_premium_users())
    
    # Get total payments
    payments = db.get_all_payments()
    total_payments = sum(p['amount'] for p in payments)
    
    # Get referral stats
    referrals = db.get_all_referrals()
    total_referrals = len(referrals)
    converted_referrals = sum(1 for r in referrals if r['converted'])
    total_commission = sum(r['commission_owed'] for r in referrals if r['converted'])
    
    # Calculate conversion rate safely
    user_conversion_rate = (premium_users/total_users*100) if total_users > 0 else 0
    referral_conversion_rate = (converted_referrals/total_referrals*100) if total_referrals > 0 else 0
    
    update.message.reply_text(
        f"📊 Admin Statistics 📊\n\n"
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
        f"• Total commission owed: {total_commission:.2f} SOL",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Export Users", callback_data="export_users")],
            [InlineKeyboardButton("Export Payments", callback_data="export_payments")],
            [InlineKeyboardButton("Export Referrals", callback_data="export_referrals")]
        ])
    )
    
    return EXPORT_DATA

@admin_required
def lookup_user(update: Update, context: CallbackContext):
    """Look up a user by Telegram ID"""
    # Check if ID was provided
    args = context.args
    if args and len(args) > 0:
        try:
            user_id = int(args[0])
            return show_user_info(update, context, user_id)
        except ValueError:
            update.message.reply_text("Please provide a valid Telegram ID.")
    
    update.message.reply_text(
        "Please enter the Telegram ID of the user you want to look up:"
    )
    
    return LOOKUP_USER

def process_lookup_user(update: Update, context: CallbackContext):
    """Process the user ID sent by the admin"""
    try:
        user_id = int(update.message.text.strip())
        return show_user_info(update, context, user_id)
    except ValueError:
        update.message.reply_text("Please provide a valid Telegram ID.")
        return LOOKUP_USER

def show_user_info(update: Update, context: CallbackContext, user_id):
    """Show information about a user"""
    db = context.dispatcher.bot_data['db']
    
    # Get user info
    user = db.get_user(user_id)
    
    if not user:
        update.message.reply_text(f"User with ID {user_id} not found.")
        return ConversationHandler.END
    
    # Get user's wallets
    wallets = db.get_wallets(user_id)
    wallet_text = "\n".join([f"• {w['solana_address']}" for w in wallets]) if wallets else "None"
    
    # Get payment history
    payments = db.get_payment_history(user_id)
    payment_text = "\n".join([
        f"• {p['amount']} SOL on {p['payment_date']} (TX: {p['transaction_id'][:5]}...{p['transaction_id'][-4:]})"
        for p in payments
    ]) if payments else "None"
    
    # Get referral info
    referral_code = db.get_referral_code(user_id)
    referral_text = f"Username: {referral_code['referral_username']}\nPayout wallet: {referral_code['payout_wallet']}" if referral_code else "None"
    
    # Get referrals made by this user
    stats = db.get_referral_stats(user_id) if referral_code else None
    referrals_made_text = f"Total: {stats['total']}\nConverted: {stats['converted']}\nCommission: {stats['total_commission']} SOL" if stats else "None"
    
    # Get who referred this user
    referrer_id = db.get_referrer(user_id)
    referrer_text = f"Referred by: {referrer_id}" if referrer_id else "Not referred"
    
    update.message.reply_text(
        f"👤 User Information 👤\n\n"
        f"ID: {user_id}\n"
        f"Username: {user['username'] or 'None'}\n"
        f"Premium: {'✅' if user['is_premium'] else '❌'}\n"
        f"Paid amount: {user['paid_amount']} SOL\n"
        f"Registration date: {user['registration_date']}\n"
        f"Last payment date: {user['last_payment_date'] or 'None'}\n\n"
        f"Wallets:\n{wallet_text}\n\n"
        f"Payment history:\n{payment_text}\n\n"
        f"Referral code:\n{referral_text}\n\n"
        f"Referrals made:\n{referrals_made_text}\n\n"
        f"{referrer_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set Premium", callback_data=f"set_premium_{user_id}")],
            [InlineKeyboardButton("Remove Premium", callback_data=f"remove_premium_{user_id}")],
            [InlineKeyboardButton("🔙 Back to Stats", callback_data="admin_stats")]
        ])
    )
    
    return ConversationHandler.END

@admin_required
def export_commissions(update: Update, context: CallbackContext):
    """Export commission data for payouts"""
    db = context.dispatcher.bot_data['db']
    
    # Get pending payouts
    payouts = db.get_referral_payouts()
    
    if not payouts:
        update.message.reply_text("No pending commission payouts found.")
        return ConversationHandler.END
    
    # Create CSV file
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Telegram ID', 'Username', 'Payout Wallet', 'Total Referrals', 'Converted Referrals', 'Commission (SOL)'])
    
    # Write data
    for p in payouts:
        writer.writerow([
            p['telegram_id'],
            p['username'] or 'Unknown',
            p['payout_wallet'],
            p['total_referrals'],
            p['converted_referrals'],
            p['total_commission']
        ])
    
    # Send file
    output.seek(0)
    date_str = datetime.now().strftime('%Y%m%d')
    filename = f"commissions_{date_str}.csv"
    
    update.message.reply_document(
        document=io.BytesIO(output.getvalue().encode()),
        filename=filename,
        caption=f"Commission data exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    return ConversationHandler.END

def export_data_callback(update: Update, context: CallbackContext):
    """Handle export data button clicks"""
    query = update.callback_query
    query.answer()
    
    db = context.dispatcher.bot_data['db']
    output = io.StringIO()
    
    if query.data == "export_users":
        # Export users
        users = db.get_all_users(limit=1000000)
        
        # Create CSV file
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Telegram ID', 'Username', 'Premium', 'Paid Amount', 'Registration Date', 'Last Payment Date'])
        
        # Write data
        for u in users:
            writer.writerow([
                u['telegram_id'],
                u['username'] or 'Unknown',
                'Yes' if u['is_premium'] else 'No',
                u['paid_amount'],
                u['registration_date'],
                u['last_payment_date'] or 'N/A'
            ])
        
        filename = f"users_{datetime.now().strftime('%Y%m%d')}.csv"
        
    elif query.data == "export_payments":
        # Export payments
        payments = db.get_all_payments()
        
        # Create CSV file
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Payment ID', 'Telegram ID', 'Wallet Address', 'Amount', 'Transaction ID', 'Payment Date'])
        
        # Write data
        for p in payments:
            writer.writerow([
                p['id'],
                p['telegram_id'],
                p['solana_address'],
                p['amount'],
                p['transaction_id'],
                p['payment_date']
            ])
        
        filename = f"payments_{datetime.now().strftime('%Y%m%d')}.csv"
        
    elif query.data == "export_referrals":
        # Export referrals
        referrals = db.get_all_referrals()
        
        # Create CSV file
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Referral ID', 'Referrer ID', 'Referee ID', 'Referral Date', 'Converted', 'Conversion Date', 'Payment Amount', 'Commission'])
        
        # Write data
        for r in referrals:
            writer.writerow([
                r['id'],
                r['referrer_id'],
                r['referee_id'],
                r['referral_date'],
                'Yes' if r['converted'] else 'No',
                r['conversion_date'] or 'N/A',
                r['payment_amount'] or 'N/A',
                r['commission_owed'] or 'N/A'
            ])
        
        filename = f"referrals_{datetime.now().strftime('%Y%m%d')}.csv"
        
    elif query.data == "admin_stats":
        # Go back to admin stats
        return admin_stats(update, context)
    
    elif query.data.startswith("set_premium_"):
        # Set user premium status
        user_id = int(query.data.split('_')[-1])
        db.set_premium_status(user_id, True)
        query.edit_message_text(f"✅ User {user_id} has been set to premium status.")
        return ConversationHandler.END
    
    elif query.data.startswith("remove_premium_"):
        # Remove user premium status
        user_id = int(query.data.split('_')[-1])
        db.set_premium_status(user_id, False)
        query.edit_message_text(f"❌ Premium status removed from user {user_id}.")
        return ConversationHandler.END
    
    else:
        query.edit_message_text("Invalid option.")
        return ConversationHandler.END
    
    # Send file
    output.seek(0)
    
    context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=io.BytesIO(output.getvalue().encode()),
        filename=filename,
        caption=f"Data exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    return ConversationHandler.END

@admin_required
def whitelist_user(update: Update, context: CallbackContext):
    """Whitelist a user by username or ID and grant premium access"""
    args = context.args
    
    if not args or len(args) == 0:
        update.message.reply_text(
            "Please provide a username or Telegram ID to whitelist.\n\n"
            "Usage: /whitelist username OR /whitelist 123456789"
        )
        return ConversationHandler.END
    
    db = context.dispatcher.bot_data['db']
    identifier = args[0]
    
    # Check if input is a numeric ID
    if identifier.isdigit():
        user_id = int(identifier)
        user = db.get_user(user_id)
        
        if not user:
            update.message.reply_text(f"User with ID {user_id} not found in database.")
            return ConversationHandler.END
            
        # Set user to premium
        db.set_premium_status(user_id, True)
        update.message.reply_text(f"✅ User with ID {user_id} has been granted premium access.")
        
    # Otherwise treat as username
    else:
        # If username starts with @, remove it
        if identifier.startswith('@'):
            identifier = identifier[1:]
        
        # Find user by username
        user = db.get_user_by_username(identifier)
        
        if not user:
            update.message.reply_text(f"User with username '{identifier}' not found in database.")
            return ConversationHandler.END
            
        # Set user to premium
        db.set_premium_status(user['telegram_id'], True)
        update.message.reply_text(f"✅ User @{identifier} has been granted premium access.")
    
    return ConversationHandler.END

# Create conversation handler for admin commands
admin_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("admin_stats", admin_stats),
        CommandHandler("lookup_user", lookup_user),
        CommandHandler("export_commissions", export_commissions),
        CommandHandler("whitelist_user", whitelist_user),
    ],
    states={
        LOOKUP_USER: [
            MessageHandler(Filters.text & ~Filters.command, process_lookup_user),
        ],
        EXPORT_DATA: [
            CallbackQueryHandler(export_data_callback),
        ],
    },
    fallbacks=[CommandHandler("admin_stats", admin_stats)],
) 