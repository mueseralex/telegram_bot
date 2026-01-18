import os
import jwt
import time
import logging
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from config import BOT_TOKEN, JWT_SECRET, WEBSITE_URL
from database import Database

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
db = Database('translucent_bot.db')

@app.route('/auth', methods=['GET'])
def authenticate():
    """Handle authentication requests from the website"""
    token = request.args.get('token')
    
    if not token:
        return jsonify({'success': False, 'error': 'No token provided'}), 400
    
    # Verify token
    user = db.verify_auth_token(token)
    
    if not user:
        return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
    
    # Generate JWT for the website
    payload = {
        'telegram_id': user['telegram_id'],
        'username': user['username'],
        'is_premium': user['is_premium'],
        'exp': int(time.time()) + 86400  # 24 hour expiration
    }
    
    jwt_token = jwt.encode(payload, JWT_SECRET, algorithm='HS256')
    
    # Redirect to website with JWT
    redirect_url = f"{WEBSITE_URL}/login?token={jwt_token}"
    return redirect(redirect_url)

@app.route('/verify_jwt', methods=['POST'])
def verify_jwt():
    """Verify a JWT token from the website"""
    try:
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'No token provided'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Decode and verify JWT
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        
        # Check if user is still premium (in case they were downgraded)
        user = db.get_user(payload['telegram_id'])
        if not user or not user['is_premium']:
            return jsonify({'success': False, 'error': 'User is not premium'}), 403
        
        return jsonify({
            'success': True,
            'user': {
                'telegram_id': user['telegram_id'],
                'username': user['username'],
                'is_premium': user['is_premium']
            }
        })
    except jwt.ExpiredSignatureError:
        return jsonify({'success': False, 'error': 'Token expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401
    except Exception as e:
        logger.error(f"Error verifying JWT: {e}")
        return jsonify({'success': False, 'error': 'Server error'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    # Clean expired tokens on startup
    cleaned = db.clean_expired_tokens()
    logger.info(f"Cleaned {cleaned} expired tokens")
    
    # Run the Flask app
    port = int(os.environ.get('AUTH_PORT', 5002))
    logger.info(f"Starting authentication server on port {port}")
    app.run(host='0.0.0.0', port=port) 