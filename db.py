import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

# For local development fallback
if not DATABASE_URL:
    DATABASE_URL = "mysql+pymysql://root:password@localhost/daily_tracker"

# Create engine
engine = create_engine(DATABASE_URL, echo=False)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Database Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)

class Activity(Base):
    __tablename__ = "activities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    category = Column(String(100), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    mood_rating = Column(Integer, nullable=True)
    photo_url = Column(String(500), nullable=True)
    activity_date = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=True)

# Context manager for database connections
@contextmanager
def get_db():
    """Context manager for database connections"""
    connection = None
    try:
        # Parse DATABASE_URL for raw connection
        if DATABASE_URL.startswith('mysql+pymysql://'):
            # Extract connection details from URL
            url_parts = DATABASE_URL.replace('mysql+pymysql://', '').split('/')
            auth_host = url_parts[0]
            database = url_parts[1] if len(url_parts) > 1 else 'daily_tracker'
            
            if '@' in auth_host:
                auth, host_port = auth_host.split('@')
                username, password = auth.split(':')
                host = host_port.split(':')[0] if ':' in host_port else host_port
                port = int(host_port.split(':')[1]) if ':' in host_port else 3306
            else:
                username, password, host, port = 'root', '', auth_host, 3306
            
            connection = mysql.connector.connect(
                host=host,
                port=port,
                user=username,
                password=password,
                database=database,
                autocommit=False
            )
        else:
            # Fallback for other formats
            connection = mysql.connector.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 3306)),
                user=os.getenv('DB_USER', 'root'),
                password=os.getenv('DB_PASSWORD', ''),
                database=os.getenv('DB_NAME', 'daily_tracker'),
                autocommit=False
            )
        
        yield connection
        
    except Exception as e:
        if connection:
            connection.rollback()
        raise e
    finally:
        if connection:
            connection.close()

def create_tables():
    """Create all tables"""
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        raise