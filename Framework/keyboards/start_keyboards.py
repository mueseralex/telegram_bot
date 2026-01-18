from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_start_keyboard(is_premium=False):
    """Get the main keyboard for the start command"""
    if is_premium:
        keyboard = {
            'inline_keyboard': [
                [{'text': "💰 Wallet Management", 'callback_data': "wallet_menu"}],
                [{'text': "🔄 Referral Program", 'callback_data': "referral_menu"}]
            ]
        }
    else:
        keyboard = {
            'inline_keyboard': [
                [{'text': "💰 Link Wallet", 'callback_data': "wallet_menu"}],
                [{'text': "💸 Pay Now", 'callback_data': "pay_now"}],
                [{'text': "🔄 Referral Program", 'callback_data': "referral_menu"}]
            ]
        }
    
    return keyboard

def get_wallet_management_keyboard(wallets=None):
    """Get keyboard for wallet management"""
    keyboard = []
    
    # Add wallet button
    keyboard.append([{'text': "➕ Add Wallet", 'callback_data': "add_wallet"}])
    
    # Remove wallet button (only if user has wallets)
    if wallets and len(wallets) > 0:
        keyboard.append([{'text': "➖ Remove Wallet", 'callback_data': "remove_wallet"}])
    
    # Pay now button
    keyboard.append([{'text': "💸 Pay Now", 'callback_data': "pay_now"}])
    
    # Back button
    keyboard.append([{'text': "🔙 Back", 'callback_data': "back_to_start"}])
    
    return {'inline_keyboard': keyboard}

def get_remove_wallet_keyboard(wallets):
    """Get keyboard for wallet removal selection"""
    keyboard = []
    
    # Add a button for each wallet
    for wallet in wallets:
        address = wallet['solana_address']
        short_address = f"{address[:5]}...{address[-4:]}"
        keyboard.append([{
            'text': f"🗑️ {short_address}", 
            'callback_data': f"remove_wallet_id_{wallet['id']}"
        }])
    
    # Back button
    keyboard.append([{'text': "🔙 Back", 'callback_data': "back_to_wallet_menu"}])
    
    return {'inline_keyboard': keyboard}

def get_confirm_remove_keyboard(wallet_id):
    """Get keyboard for confirming wallet removal"""
    keyboard = {
        'inline_keyboard': [
            [{'text': "✅ Yes, Remove", 'callback_data': f"confirm_remove_{wallet_id}"}],
            [{'text': "❌ No, Cancel", 'callback_data': "cancel_remove"}]
        ]
    }
    
    return keyboard 