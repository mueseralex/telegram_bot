from flask import Flask, request, jsonify
import requests
import logging
import json
from config import BOT_TOKEN, REQUIRED_PAYMENT, COMMISSION_PERCENTAGE, DEPOSIT_ADDRESS
from database import Database

app = Flask(__name__)
db = Database('translucent_bot.db')

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
                
                # Get user's total paid amount
                user = db.get_user(user_id)
                paid_amount = user['paid_amount'] if user else 0
                logger.info(f"User {user_id} total paid amount: {paid_amount}")
                
                # Check if payment is sufficient for premium access
                if paid_amount >= REQUIRED_PAYMENT:
                    logger.info(f"User {user_id} has paid enough for premium access")
                    # Set user to premium
                    db.set_premium_status(user_id, True)
                    
                    # Process referral if exists
                    referrer_id = db.convert_referral(user_id, amount_sol, COMMISSION_PERCENTAGE)
                    
                    # Send notification to user
                    send_telegram_message(user_id, 
                        "🎉 <b>Payment Confirmed!</b> 🎉\n\n"
                        "You now have full access to all premium features."
                    )
                    
                    # Send notification to referrer if exists
                    if referrer_id:
                        referral_stats = db.get_referral_stats(referrer_id)
                        send_telegram_message(referrer_id,
                            "🎉 <b>Referral Converted!</b> 🎉\n\n"
                            f"You earned {amount_sol * (COMMISSION_PERCENTAGE/100):.3f} SOL in commission.\n\n"
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

# Add a simple route to check if the server is running
@app.route('/', methods=['GET'])
def index():
    return "Webhook server is running"

@app.route('/test_payment', methods=['GET'])
def test_payment():
    """Test route to verify the payment webhook server is running"""
    return jsonify({
        'status': 'success',
        'message': 'Payment webhook server is running',
        'deposit_address': DEPOSIT_ADDRESS
    })

if __name__ == '__main__':
    logger.info(f"Starting payment webhook server with deposit address: {DEPOSIT_ADDRESS}")
    app.run(host='0.0.0.0', port=5001, debug=True) 