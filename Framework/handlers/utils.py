"""Utility functions for handlers"""

def format_wallet_address(address, show_chars=4):
    """Format a wallet address to show only the beginning and end"""
    if not address or len(address) <= show_chars * 2:
        return address
    return f"{address[:show_chars]}...{address[-show_chars:]}"

def format_sol_amount(amount):
    """Format a SOL amount with proper precision"""
    return f"{amount:.4f}"

def validate_solana_address(address):
    """Basic validation for Solana addresses"""
    import re
    # Solana addresses are base58 encoded and typically 32-44 characters
    return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))

def get_commission_amount(payment_amount, percentage=5.0):
    """Calculate commission amount based on payment and percentage"""
    return payment_amount * (percentage / 100) 