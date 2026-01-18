from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_referral_keyboard(has_referral=False):
    """Get the main keyboard for the referral command"""
    if has_referral:
        keyboard = {
            'inline_keyboard': [
                [{'text': "Change Payout Wallet", 'callback_data': "change_payout_wallet"}],
                [{'text': "View Detailed Stats", 'callback_data': "view_detailed_stats"}],
                [{'text': "🔙 Back to Menu", 'callback_data': "back_to_start"}]
            ]
        }
    else:
        keyboard = {
            'inline_keyboard': [
                [{'text': "Create Referral Link", 'callback_data': "create_referral"}],
                [{'text': "🔙 Back to Menu", 'callback_data': "back_to_start"}]
            ]
        }
    
    return keyboard

def get_referral_stats_keyboard():
    """Get keyboard for referral stats"""
    keyboard = {
        'inline_keyboard': [
            [{'text': "View Detailed Stats", 'callback_data': "view_detailed_stats"}],
            [{'text': "Change Payout Wallet", 'callback_data': "change_payout_wallet"}],
            [{'text': "🔙 Back to Menu", 'callback_data': "back_to_start"}]
        ]
    }
    
    return keyboard 