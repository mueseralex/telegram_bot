import jwt
import time
import logging
from flask import request, jsonify, redirect
from config import JWT_SECRET, WEBSITE_URL, AUTH_TOKEN_EXPIRY
from database import Database

# Set up logging
logger = logging.getLogger(__name__)
db = Database('translucent_bot.db')

def setup_auth_routes(app):
    """Set up authentication routes on the given Flask app"""
    
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
        
        # Redirect to premium or landing page based on premium status
        if user['is_premium']:
            redirect_url = f"{WEBSITE_URL}/premium/login?token={jwt_token}"
        else:
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
    
    # Clean expired tokens on startup
    cleaned = db.clean_expired_tokens()
    logger.info(f"Cleaned {cleaned} expired tokens")

    @app.route('/generate_auth_token', methods=['GET'])
    def generate_auth_token():
        """Generate an authentication token for Telegram login"""
        user_id = request.args.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Missing user_id parameter'}), 400
        
        # Get user info
        user = db.get_user(int(user_id))
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Generate token
        token_data = db.generate_auth_token(int(user_id), AUTH_TOKEN_EXPIRY)
        
        if not token_data:
            return jsonify({'error': 'Failed to generate token'}), 500
        
        # Redirect to website with token
        redirect_url = f"{WEBSITE_URL}?token={token_data['token']}"
        return redirect(redirect_url)
    
    @app.route('/verify_token', methods=['GET'])
    def verify_token():
        """Verify an authentication token"""
        token = request.args.get('token')
        
        if not token:
            return jsonify({'valid': False, 'error': 'Missing token parameter'}), 400
        
        # Verify token
        user = db.verify_auth_token(token)
        
        if not user:
            return jsonify({'valid': False, 'error': 'Invalid or expired token'}), 401
        
        # Return user info
        return jsonify({
            'valid': True,
            'user': {
                'telegram_id': user['telegram_id'],
                'username': user['username'],
                'is_premium': bool(user['is_premium']),
                'paid_amount': user['paid_amount']
            }
        })
    
    @app.route('/web_auth_command', methods=['GET'])
    def web_auth_command():
        """Handle the web_auth command from Telegram"""
        user_id = request.args.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Missing user_id parameter'}), 400
        
        # Generate auth URL
        auth_url = f"{app.config['SERVER_URL']}/generate_auth_token?user_id={user_id}"
        
        return jsonify({
            'auth_url': auth_url,
            'message': 'Click the link below to authenticate on the website'
        })

    logger.info("Auth routes configured") 