from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os
import time
import uuid
import datetime
import logging
from contextlib import contextmanager
import sqlite3  # Still needed for direct migrations

logger = logging.getLogger(__name__)
Base = declarative_base()

class Database:
    def __init__(self, db_name=None):
        # Use environment variable for database URL in production
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            # Fallback to SQLite for local development
            self.db_path = db_name  # Keep for backward compatibility
            db_url = f'sqlite:///{db_name}'
            self.is_sqlite = True
        else:
            self.is_sqlite = False
        
        logger.info(f"Connecting to database: {db_url.split('@')[0] if '@' in db_url else db_url}")
        
        # Create engine with connection pooling if not SQLite
        if self.is_sqlite:
            # SQLite doesn't need pooling parameters
            self.engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False}  # Allow multi-threaded access
            )
        else:
            # PostgreSQL and other databases support pooling
            self.engine = create_engine(
                db_url,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30,
                pool_recycle=1800,  # Recycle connections after 30 minutes
                pool_pre_ping=True  # Verify connections before using them
            )
        
        # Create session factory
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        # Initialize database if needed
        self.init_db()
    
    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()
    
    def init_db(self):
        """Initialize database tables if they don't exist"""
        metadata = MetaData()
        
        # Define tables
        users = Table('users', metadata,
            Column('id', Integer, primary_key=True),
            Column('telegram_id', Integer, unique=True, nullable=False, index=True),
            Column('username', String),
            Column('is_premium', Boolean, default=False),
            Column('paid_amount', Float, default=0),
            Column('referral_code', String, unique=True, index=True),
            Column('state', String),
            Column('payout_wallet', String),
            Column('total_commission', Float, default=0),
            Column('created_at', DateTime),
            Column('updated_at', DateTime)
        )
        
        wallets = Table('wallets', metadata,
            Column('id', Integer, primary_key=True),
            Column('telegram_id', Integer, nullable=False, index=True),
            Column('solana_address', String, nullable=False, index=True),
            Column('created_at', DateTime)
        )
        
        payments = Table('payments', metadata,
            Column('id', Integer, primary_key=True),
            Column('telegram_id', Integer, nullable=False, index=True),
            Column('amount', Float, nullable=False),
            Column('transaction_id', String, nullable=False, unique=True, index=True),
            Column('payment_date', DateTime, index=True)
        )
        
        referrals = Table('referrals', metadata,
            Column('id', Integer, primary_key=True),
            Column('referrer_id', Integer, nullable=False, index=True),
            Column('referred_id', Integer, nullable=False, index=True, unique=True),
            Column('converted', Boolean, default=False),
            Column('commission_amount', Float, default=0),
            Column('created_at', DateTime)
        )
        
        referral_codes = Table('referral_codes', metadata,
            Column('id', Integer, primary_key=True),
            Column('telegram_id', Integer, nullable=False, index=True, unique=True),
            Column('code', String, nullable=False, unique=True, index=True),
            Column('created_at', DateTime)
        )
        
        auth_tokens = Table('auth_tokens', metadata,
            Column('id', Integer, primary_key=True),
            Column('telegram_id', Integer, nullable=False, index=True),
            Column('token', String, nullable=False, unique=True, index=True),
            Column('expires_at', DateTime, nullable=False, index=True),
            Column('created_at', DateTime),
            Column('used', Boolean, default=False)
        )
        
        # Create tables if they don't exist
        metadata.create_all(self.engine)
        logger.info("Database initialized")

    # --- User Management Methods ---
    
    def add_user_if_not_exists(self, telegram_id, username=None):
        """Add a user to the database if they don't exist"""
        with self.session_scope() as session:
            # Check if user exists
            result = session.execute(
                text("SELECT telegram_id FROM users WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            if not result:
                # User doesn't exist, add them
                now = datetime.datetime.now()
                session.execute(
                    text("""
                        INSERT INTO users (telegram_id, username, is_premium, paid_amount, created_at, updated_at)
                        VALUES (:telegram_id, :username, 0, 0, :created_at, :updated_at)
                    """),
                    {
                        "telegram_id": telegram_id,
                        "username": username,
                        "created_at": now,
                        "updated_at": now
                    }
                )
                logger.info(f"Added new user: {telegram_id}")
                return True
            return False
    
    def get_user(self, telegram_id):
        """Get user information"""
        with self.session_scope() as session:
            result = session.execute(
                text("SELECT * FROM users WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            if result:
                # Convert to dict
                return {col: getattr(result, col) for col in result._mapping.keys()}
            return None
    
    def set_user_premium(self, telegram_id, amount):
        """Set user as premium and record payment amount"""
        with self.session_scope() as session:
            now = datetime.datetime.now()
            session.execute(
                text("""
                    UPDATE users 
                    SET is_premium = 1, 
                        paid_amount = paid_amount + :amount,
                        updated_at = :updated_at
                    WHERE telegram_id = :telegram_id
                """),
                {
                    "telegram_id": telegram_id,
                    "amount": amount,
                    "updated_at": now
                }
            )
            
            # Check if this user was referred by someone
            referral = session.execute(
                text("SELECT referrer_id FROM referrals WHERE referred_id = :referred_id AND converted = 0"),
                {"referred_id": telegram_id}
            ).fetchone()
            
            if referral:
                referrer_id = referral[0]
                commission_amount = amount * 0.2  # 20% commission
                
                # Mark referral as converted
                session.execute(
                    text("""
                        UPDATE referrals 
                        SET converted = 1, 
                            commission_amount = :commission_amount 
                        WHERE referrer_id = :referrer_id AND referred_id = :referred_id
                    """),
                    {
                        "referrer_id": referrer_id,
                        "referred_id": telegram_id,
                        "commission_amount": commission_amount
                    }
                )
                
                # Update referrer's total commission
                session.execute(
                    text("""
                        UPDATE users 
                        SET total_commission = total_commission + :commission_amount 
                        WHERE telegram_id = :telegram_id
                    """),
                    {
                        "telegram_id": referrer_id,
                        "commission_amount": commission_amount
                    }
                )
                
                logger.info(f"Converted referral: {telegram_id} paid, {referrer_id} earned {commission_amount}")
                
                return True, referrer_id, commission_amount
            
            return True, None, 0
    
    def set_user_state(self, telegram_id, state):
        """Set user state for conversation handling"""
        with self.session_scope() as session:
            session.execute(
                text("UPDATE users SET state = :state WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id, "state": state}
            )
            return True
    
    def get_user_state(self, telegram_id):
        """Get user state for conversation handling"""
        with self.session_scope() as session:
            result = session.execute(
                text("SELECT state FROM users WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            if result and result[0]:
                return result[0]
            return None

    # --- Wallet Management Methods ---
    
    def add_wallet(self, telegram_id, wallet_address):
        """Add a wallet to the user"""
        with self.session_scope() as session:
            # Check if wallet already exists for this user
            result = session.execute(
                text("""
                    SELECT id FROM wallets 
                    WHERE telegram_id = :telegram_id AND solana_address = :wallet_address
                """),
                {"telegram_id": telegram_id, "wallet_address": wallet_address}
            ).fetchone()
            
            if result:
                return False  # Wallet already exists
            
            # Add wallet
            now = datetime.datetime.now()
            session.execute(
                text("""
                    INSERT INTO wallets (telegram_id, solana_address, created_at)
                    VALUES (:telegram_id, :wallet_address, :created_at)
                """),
                {
                    "telegram_id": telegram_id,
                    "wallet_address": wallet_address,
                    "created_at": now
                }
            )
            
            return True
    
    def get_user_wallets(self, telegram_id):
        """Get all wallets for a user"""
        with self.session_scope() as session:
            results = session.execute(
                text("SELECT * FROM wallets WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchall()
            
            if results:
                return [{col: getattr(row, col) for col in row._mapping.keys()} for row in results]
            return []
    
    def remove_wallet(self, telegram_id, wallet_address):
        """Remove a wallet from the user"""
        with self.session_scope() as session:
            session.execute(
                text("""
                    DELETE FROM wallets 
                    WHERE telegram_id = :telegram_id AND solana_address = :wallet_address
                """),
                {"telegram_id": telegram_id, "wallet_address": wallet_address}
            )
            
            return True

    # --- Payment Methods ---
    
    def add_payment(self, telegram_id, transaction_id, amount):
        """Record a payment from a user"""
        with self.session_scope() as session:
            try:
                # Check if this transaction has already been processed
                existing = session.execute(
                    text("SELECT id FROM payments WHERE transaction_id = :transaction_id"),
                    {"transaction_id": transaction_id}
                ).fetchone()
                
                if existing:
                    logger.warning(f"Transaction {transaction_id} has already been processed")
                    return False
                
                # Add payment record
                now = datetime.datetime.now()
                session.execute(
                    text("""
                        INSERT INTO payments (telegram_id, amount, transaction_id, payment_date)
                        VALUES (:telegram_id, :amount, :transaction_id, :payment_date)
                    """),
                    {
                        "telegram_id": telegram_id,
                        "amount": amount,
                        "transaction_id": transaction_id,
                        "payment_date": now
                    }
                )
                
                # Update user's paid amount and premium status
                session.execute(
                    text("""
                        UPDATE users 
                        SET paid_amount = paid_amount + :amount,
                            is_premium = 1,
                            updated_at = :updated_at
                        WHERE telegram_id = :telegram_id
                    """),
                    {
                        "telegram_id": telegram_id,
                        "amount": amount,
                        "updated_at": now
                    }
                )
                
                # Check if this user was referred by someone
                referral = session.execute(
                    text("SELECT referrer_id FROM referrals WHERE referred_id = :referred_id AND converted = 0"),
                    {"referred_id": telegram_id}
                ).fetchone()
                
                if referral:
                    referrer_id = referral[0]
                    commission_amount = amount * 0.2  # 20% commission
                    
                    # Mark referral as converted
                    session.execute(
                        text("""
                            UPDATE referrals 
                            SET converted = 1, 
                                commission_amount = :commission_amount 
                            WHERE referrer_id = :referrer_id AND referred_id = :referred_id
                        """),
                        {
                            "referrer_id": referrer_id,
                            "referred_id": telegram_id,
                            "commission_amount": commission_amount
                        }
                    )
                    
                    # Update referrer's total commission
                    session.execute(
                        text("""
                            UPDATE users 
                            SET total_commission = total_commission + :amount 
                            WHERE telegram_id = :telegram_id
                        """),
                        {
                            "telegram_id": referrer_id,
                            "amount": commission_amount
                        }
                    )
                    
                    logger.info(f"Added commission of {commission_amount} SOL to user {referrer_id}")
                
                logger.info(f"Payment of {amount} SOL recorded for user {telegram_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error adding payment: {e}")
                return False
    
    def get_user_payments(self, telegram_id):
        """Get all payments for a user"""
        with self.session_scope() as session:
            results = session.execute(
                text("SELECT * FROM payments WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchall()
            
            if results:
                return [{col: getattr(row, col) for col in row._mapping.keys()} for row in results]
            return []

    # --- Referral Methods ---
    
    def create_referral_code(self, telegram_id, code):
        """Create a referral code for the user"""
        with self.session_scope() as session:
            # Check if user already has a referral code
            result = session.execute(
                text("SELECT code FROM referral_codes WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            if result:
                return False, result[0]  # User already has a code
            
            # Check if code is already taken
            result = session.execute(
                text("SELECT telegram_id FROM referral_codes WHERE code = :code"),
                {"code": code}
            ).fetchone()
            
            if result:
                return False, None  # Code already taken
            
            # Create referral code
            now = datetime.datetime.now()
            session.execute(
                text("""
                    INSERT INTO referral_codes (telegram_id, code, created_at)
                    VALUES (:telegram_id, :code, :created_at)
                """),
                {
                    "telegram_id": telegram_id,
                    "code": code,
                    "created_at": now
                }
            )
            
            return True, code
    
    def get_referral_code(self, telegram_id):
        """Get the referral code for a user"""
        with self.session_scope() as session:
            result = session.execute(
                text("SELECT code FROM referral_codes WHERE telegram_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            if result:
                return result[0]
            return None
    
    def record_referral(self, referrer_id, referred_id):
        """Record a referral relationship"""
        with self.session_scope() as session:
            # Check if referred user already has a referrer
            result = session.execute(
                text("SELECT id FROM referrals WHERE referred_id = :referred_id"),
                {"referred_id": referred_id}
            ).fetchone()
            
            if result:
                return False  # User already has a referrer
            
            # Record referral
            now = datetime.datetime.now()
            session.execute(
                text("""
                    INSERT INTO referrals (referrer_id, referred_id, converted, commission_amount, created_at)
                    VALUES (:referrer_id, :referred_id, 0, 0, :created_at)
                """),
                {
                    "referrer_id": referrer_id,
                    "referred_id": referred_id,
                    "created_at": now
                }
            )
            
            return True
    
    def get_referral_stats(self, telegram_id):
        """Get referral statistics for a user"""
        with self.session_scope() as session:
            # Get total referrals
            total_result = session.execute(
                text("SELECT COUNT(*) FROM referrals WHERE referrer_id = :telegram_id"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            # Get converted referrals
            converted_result = session.execute(
                text("SELECT COUNT(*) FROM referrals WHERE referrer_id = :telegram_id AND converted = 1"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            # Get total commission
            commission_result = session.execute(
                text("SELECT SUM(commission_amount) FROM referrals WHERE referrer_id = :telegram_id AND converted = 1"),
                {"telegram_id": telegram_id}
            ).fetchone()
            
            return {
                "total_referrals": total_result[0] if total_result else 0,
                "converted_referrals": converted_result[0] if converted_result else 0,
                "total_commission": commission_result[0] if commission_result and commission_result[0] else 0
            }
    
    def get_user_referrals(self, telegram_id):
        """Get all referrals for a user"""
        with self.session_scope() as session:
            results = session.execute(
                text("""
                    SELECT r.*, u.username 
                    FROM referrals r
                    LEFT JOIN users u ON r.referred_id = u.telegram_id
                    WHERE r.referrer_id = :telegram_id
                    ORDER BY r.created_at DESC
                """),
                {"telegram_id": telegram_id}
            ).fetchall()
            
            if results:
                return [{col: getattr(row, col) for col in row._mapping.keys()} for row in results]
            return []
    
    def get_user_by_referral_code(self, referral_code):
        """Get user ID by referral code"""
        with self.session_scope() as session:
            # Look up the referral code in the referral_codes table
            result = session.execute(
                text("SELECT telegram_id FROM referral_codes WHERE code = :code"),
                {"code": referral_code}
            ).fetchone()
            
            if result:
                logger.info(f"Found user by referral code: {referral_code}")
                return result[0]
            
            # If not found, try to find by telegram_id (for backward compatibility)
            try:
                # Check if the code is a numeric ID
                user_id = int(referral_code)
                result = session.execute(
                    text("SELECT telegram_id FROM users WHERE telegram_id = :telegram_id"),
                    {"telegram_id": user_id}
                ).fetchone()
                
                if result:
                    logger.info(f"Found user by telegram_id: {user_id}")
                    return result[0]
            except ValueError:
                # Not a numeric ID, ignore
                pass
            
            logger.warning(f"No user found with referral code: {referral_code}")
            return None

    # --- Authentication Methods ---
    
    def generate_auth_token(self, telegram_id, expiry_seconds):
        """Generate an authentication token for a user"""
        with self.session_scope() as session:
            # Generate a unique token
            token = str(uuid.uuid4())
            
            # Calculate expiry time
            now = datetime.datetime.now()
            expires_at = now + datetime.timedelta(seconds=expiry_seconds)
            
            # Store token in database
            session.execute(
                text("""
                    INSERT INTO auth_tokens (telegram_id, token, expires_at, created_at, used)
                    VALUES (:telegram_id, :token, :expires_at, :created_at, 0)
                """),
                {
                    "telegram_id": telegram_id,
                    "token": token,
                    "expires_at": expires_at,
                    "created_at": now
                }
            )
            
            return {
                "token": token,
                "expires_at": expires_at.isoformat()
            }
    
    def verify_auth_token(self, token):
        """Verify an authentication token and return user info if valid"""
        with self.session_scope() as session:
            # Get token from database
            now = datetime.datetime.now()
            result = session.execute(
                text("""
                    SELECT * FROM auth_tokens 
                    WHERE token = :token AND used = 0 AND expires_at > :now
                """),
                {"token": token, "now": now}
            ).fetchone()
            
            if not result:
                return None
            
            # Convert to dict
            token_data = {col: getattr(result, col) for col in result._mapping.keys()}
            
            # Mark token as used
            session.execute(
                text("UPDATE auth_tokens SET used = 1 WHERE id = :id"),
                {"id": token_data['id']}
            )
            
            # Get user data
            user = self.get_user(token_data['telegram_id'])
            
            return user
    
    def clean_expired_tokens(self):
        """Remove expired tokens from the database"""
        with self.session_scope() as session:
            now = datetime.datetime.now()
            
            # Check if 'used' column exists in the auth_tokens table
            try:
                # Try to query with the used column
                session.execute(text("SELECT used FROM auth_tokens LIMIT 1"))
                has_used_column = True
            except Exception:
                has_used_column = False
            
            # Use appropriate query based on schema
            if has_used_column:
                result = session.execute(
                    text("DELETE FROM auth_tokens WHERE expires_at < :now OR used = 1"),
                    {"now": now}
                )
            else:
                # If the column doesn't exist, just filter by expiration
                result = session.execute(
                    text("DELETE FROM auth_tokens WHERE expires_at < :now"),
                    {"now": now}
                )
            
            # Add the missing column if it doesn't exist
            if not has_used_column:
                try:
                    session.execute(text("ALTER TABLE auth_tokens ADD COLUMN used BOOLEAN DEFAULT 0"))
                    logger.info("Added 'used' column to auth_tokens table")
                except Exception as e:
                    logger.error(f"Error adding 'used' column: {e}")
            
            return result.rowcount

    # --- Admin Methods ---
    
    def get_all_users(self):
        """Get all users for admin purposes"""
        with self.session_scope() as session:
            results = session.execute(text("SELECT * FROM users")).fetchall()
            if results:
                return [{col: getattr(row, col) for col in row._mapping.keys()} for row in results]
            return []
    
    def get_premium_stats(self):
        """Get premium user statistics"""
        with self.session_scope() as session:
            total_users = session.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
            premium_users = session.execute(text("SELECT COUNT(*) FROM users WHERE is_premium = 1")).fetchone()[0]
            total_payments = session.execute(text("SELECT SUM(amount) FROM payments")).fetchone()[0] or 0
            
            return {
                "total_users": total_users,
                "premium_users": premium_users,
                "premium_percentage": (premium_users / total_users * 100) if total_users > 0 else 0,
                "total_payments": total_payments
            }
    
    def add_missing_columns(self):
        """Add any missing columns to the database tables"""
        # This method is not needed with SQLAlchemy schema - metadata.create_all() handles this
        logger.info("Using SQLAlchemy schema management - no need to manually add columns")
        return True
    
    def debug_schema(self):
        """Debug database schema"""
        with self.session_scope() as session:
            tables = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            schema = {}
            
            for table in tables:
                table_name = table[0]
                columns = session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
                schema[table_name] = [{col: getattr(column, col) for col in column._mapping.keys()} for column in columns]
            
            return schema

    def get_user_by_wallet(self, wallet_address):
        """Get user ID by wallet address"""
        with self.session_scope() as session:
            result = session.execute(
                text("SELECT telegram_id FROM wallets WHERE solana_address = :address"),
                {"address": wallet_address}
            ).fetchone()
            
            if result:
                logger.info(f"Found user by wallet address: {wallet_address}")
                return result[0]
            
            logger.warning(f"No user found with wallet address: {wallet_address}")
            return None

# Initialize database if run directly
if __name__ == "__main__":
    from config import DATABASE_PATH
    db = Database(DATABASE_PATH)
    print(f"Database initialized at {DATABASE_PATH}") 