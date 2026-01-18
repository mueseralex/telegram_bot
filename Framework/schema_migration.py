from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, Boolean, DateTime, ForeignKey
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print("Error: DATABASE_URL environment variable not set")
    exit(1)

# Create engine
engine = create_engine(db_url)
metadata = MetaData()

# Define tables
users = Table('users', metadata,
    Column('id', Integer, primary_key=True),
    Column('telegram_id', Integer, unique=True, nullable=False),
    Column('username', String),
    Column('is_premium', Boolean, default=False),
    Column('paid_amount', Float, default=0),
    Column('referral_code', String, unique=True),
    Column('state', String),
    Column('payout_wallet', String),
    Column('created_at', DateTime),
    Column('updated_at', DateTime)
)

wallets = Table('wallets', metadata,
    Column('id', Integer, primary_key=True),
    Column('telegram_id', Integer, nullable=False),
    Column('solana_address', String, nullable=False),
    Column('created_at', DateTime)
)

payments = Table('payments', metadata,
    Column('id', Integer, primary_key=True),
    Column('telegram_id', Integer, nullable=False),
    Column('amount', Float, nullable=False),
    Column('transaction_id', String, nullable=False),
    Column('payment_date', DateTime)
)

referrals = Table('referrals', metadata,
    Column('id', Integer, primary_key=True),
    Column('referrer_id', Integer, nullable=False),
    Column('referred_id', Integer, nullable=False),
    Column('converted', Boolean, default=False),
    Column('commission_amount', Float, default=0),
    Column('created_at', DateTime)
)

auth_tokens = Table('auth_tokens', metadata,
    Column('id', Integer, primary_key=True),
    Column('telegram_id', Integer, nullable=False),
    Column('token', String, nullable=False),
    Column('expires_at', DateTime, nullable=False),
    Column('created_at', DateTime)
)

# Create tables
print("Creating tables...")
metadata.create_all(engine)
print("Tables created successfully!") 