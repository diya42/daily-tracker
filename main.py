from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import mysql.connector
from mysql.connector import Error
import hashlib
import jwt
import os
from contextlib import contextmanager
import json
import re
from fastapi import status
from pydantic import validator
from fastapi.staticfiles import StaticFiles


# Initialize FastAPI app
app = FastAPI(title="Daily Tracker API", version="1.0.0")

# Security
security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MySQL Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3307)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'siya1'),
    'database': os.getenv('DB_NAME', 'daily_tracker'),
    'charset': 'utf8mb4',
    'use_unicode': True,
    'autocommit': True
}

def init_db():
    """Initialize the database with required tables"""
    conn = None
    try:
        temp_config = DB_CONFIG.copy()
        database_name = temp_config.pop('database')

        conn = mysql.connector.connect(**temp_config)
        cursor = conn.cursor()

        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name}")
        cursor.execute(f"USE {database_name}")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                age INT,
                gender VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE, 
                last_login TIMESTAMP 
                
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                category VARCHAR(255) NOT NULL,
                duration_minutes INT NOT NULL,
                notes TEXT,
                mood_rating INT,

                activity_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        print("Database initialized successfully!")

    except Error as e:
        print(f"Error initializing database: {e}")
        raise RuntimeError(f"Database initialization failed: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@contextmanager
def get_db():
    """Database context manager"""
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        yield conn
    except Error as e:
        print(f"Database connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()

# Pydantic models

class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8, max_length=100, description="Password must be at least 8 characters")
    name: str = Field(..., min_length=2, max_length=100, description="Name must be between 2-100 characters")
    age: Optional[int] = Field(None, ge=13, le=120, description="Age must be between 13-120")
    gender: Optional[str] = Field(None, max_length=50)

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain at least one letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        return v

    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty')
        if not re.match(r'^[a-zA-Z\s]+$', v.strip()):
            raise ValueError('Name can only contain letters and spaces')
        return v.strip()

class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=1, description="Password is required")

    @validator('email')
    def validate_email_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Email is required')
        return v.strip().lower()

    @validator('password')
    def validate_password_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Password is required')
        return v

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    age: Optional[int] = Field(None, ge=13, le=120)
    gender: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError('Name cannot be empty')
            if not re.match(r'^[a-zA-Z\s]+$', v.strip()):
                raise ValueError('Name can only contain letters and spaces')
            return v.strip()
        return v

class PasswordUpdate(BaseModel):
    current_password: str = Field(..., min_length=1, description="Current password is required")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password must be at least 8 characters")

    @validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('New password must be at least 8 characters long')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('New password must contain at least one letter')
        if not re.search(r'\d', v):
            raise ValueError('New password must contain at least one number')
        return v

class ActivityCreate(BaseModel):
    category: str = Field(..., description="Activity category")
    duration_minutes: int = Field(..., ge=1, le=1440, description="Duration must be between 1-1440 minutes (24 hours)")
    notes: Optional[str] = Field(None, max_length=1000)
    mood_rating: Optional[int] = Field(None, ge=1, le=5, description="Mood rating 1-5")
    photo_url: Optional[str] = None
    activity_date: Optional[date] = None

    @validator('category')
    def validate_category(cls, v):
        if not v or not v.strip():
            raise ValueError('Category is required')
        return v.strip()

class ActivityResponse(BaseModel):
    id: int
    category: str
    duration_minutes: int
    notes: Optional[str]
    mood_rating: Optional[int]
    photo_url: Optional[str]
    activity_date: date
    created_at: datetime

class DailySummary(BaseModel):
    date: date
    total_logged_minutes: int
    categories: Dict[str, Dict[str, Any]]
    completion_percentage: float

class TrendData(BaseModel):
    category: str
    weekly_average: float
    monthly_average: float
    streak_days: int
    data_points: List[Dict[str, Any]]
# Predefined categories
CATEGORIES = {
    "Sleep": {"icon": "🛏", "color": "#667eea"},
    "Physical Activity/Exercise": {"icon": "🏃‍♂", "color": "#764ba2"},
    "Nutrition/Meals": {"icon": "🍎", "color": "#f093fb"},
    "Work/Productivity": {"icon": "💼", "color": "#f5576c"},
    "Personal Care/Hygiene": {"icon": "🧼", "color": "#4facfe"},
    "Social/Leisure": {"icon": "🎉", "color": "#00d4aa"},
    "Household Chores/Maintenance": {"icon": "🧹", "color": "#ff6b6b"},
    "Mindfulness/Mental Well-being": {"icon": "🧘‍♀", "color": "#a8e6cf"},
    "Transportation/Commute": {"icon": "🚗", "color": "#ffd93d"},
    "Learning/Skill Development": {"icon": "📚", "color": "#6c5ce7"}
}

# Utility functions

def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = "daily_tracker_salt"  # In production, use a proper random salt per user
    return hashlib.sha256((password + salt).encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed

def create_token(user_id: int) -> str:
    """Create JWT token with user info"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=30),
        "iat": datetime.utcnow(),
        "type": "access_token"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """Verify JWT token and return user_id with enhanced validation"""
    try:
        if not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        token_type = payload.get("type")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: user_id missing",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if token_type != "access_token":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify user still exists and is active
        with get_db() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, is_active FROM users WHERE id = %s",
                (user_id,)
            )
            user = cursor.fetchone()
            
            if not user or not user.get('is_active', True):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is inactive or deleted",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
            headers={"WWW-Authenticate": "Bearer"},
        )
# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Daily Tracker API is running with MySQL", 
        "status": "healthy",
        "version": "1.0.0",
        "documentation": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "healthy", "database": "connected", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e), "timestamp": datetime.utcnow().isoformat()}

@app.get("/categories")
async def get_categories():
    """Get all available categories"""
    return {"categories": CATEGORIES}

# ===== AUTHENTICATION ENDPOINTS =====

@app.post("/auth/register")
async def register(user: UserCreate):
    """Register a new user with enhanced validation"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(dictionary=True)
            
            # Check if user already exists
            cursor.execute("SELECT id FROM users WHERE email = %s", (user.email.lower(),))
            if cursor.fetchone() is  not None:
                  return {"detail": "User already exists."}
               

            
            
                
            
            # Create new user
            password_hash = hash_password(user.password)
            cursor.execute(
                """INSERT INTO users (email, password_hash, name, age, gender, is_active) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (user.email.lower(), password_hash, user.name, user.age, user.gender, True)
            )
            
            

            user_id = cursor.lastrowid
            conn.commit()
            
            
            # Create token
            token = create_token(user_id)
            
            return {
                "message": "User registered successfully",
                "token": token,
                "user": {
                    "id": user_id,
                    "email": user.email.lower(),
                    "name": user.name
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

    

@app.post("/auth/login")
async def login(user: UserLogin):
    """Login user with enhanced validation"""
    try:
        with get_db() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, password_hash, name, is_active FROM users WHERE email = %s",
                (user.email.lower(),)
            )
            db_user = cursor.fetchone()
            
            # Check if user exists
            if not db_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            # Check if account is active
            if not db_user.get('is_active', True):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Account is deactivated"
                )
            
            # Verify password
            if not verify_password(user.password, db_user['password_hash']):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
            
            # Update last login
            cursor.execute(
                "UPDATE users SET last_login = %s WHERE id = %s",
                (datetime.utcnow(), db_user['id'])
            )
            conn.commit()
            
            # Create token
            token = create_token(db_user['id'])
            
            return {
                "message": "Login successful",
                "token": token,
                "user": {
                    "id": db_user['id'],
                    "email": user.email.lower(),
                    "name": db_user['name']
                }
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

# ===== USER MANAGEMENT ENDPOINTS =====

@app.get("/auth/profile")
async def get_user_profile(user_id: int = Depends(verify_token)):
    """Get current user profile"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, email, name, age, gender, created_at FROM users WHERE id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "user": {
                "id": user['id'],
                "email": user['email'],
                "name": user['name'],
                "age": user['age'],
                "gender": user['gender'],
                "created_at": user['created_at'].isoformat() if user['created_at'] else None
            }
        }

@app.put("/auth/profile")
async def update_user_profile(user_update: UserUpdate, user_id: int = Depends(verify_token)):
    """Update user profile information"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Build dynamic update query
        update_fields = []
        update_values = []
        
        if user_update.name is not None:
            update_fields.append("name = %s")
            update_values.append(user_update.name)
        
        if user_update.age is not None:
            update_fields.append("age = %s")
            update_values.append(user_update.age)
        
        if user_update.gender is not None:
            update_fields.append("gender = %s")
            update_values.append(user_update.gender)
        
        if user_update.email is not None:
            # Check if email already exists for another user
            cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", 
                          (user_update.email, user_id))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Email already exists")
            
            update_fields.append("email = %s")
            update_values.append(user_update.email)
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Add user_id for WHERE clause
        update_values.append(user_id)
        
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(query, update_values)
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        conn.commit()
        
        # Return updated user info
        cursor.execute(
            "SELECT id, email, name, age, gender FROM users WHERE id = %s",
            (user_id,)
        )
        updated_user = cursor.fetchone()
        
        return {
            "message": "Profile updated successfully",
            "user": {
                "id": updated_user['id'],
                "email": updated_user['email'],
                "name": updated_user['name'],
                "age": updated_user['age'],
                "gender": updated_user['gender']
            }
        }

@app.put("/auth/password")
async def update_password(password_update: PasswordUpdate, user_id: int = Depends(verify_token)):
    """Update user password"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Get current password hash
        cursor.execute(
            "SELECT password_hash FROM users WHERE id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify current password
        if not verify_password(password_update.current_password, user['password_hash']):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Update password
        new_password_hash = hash_password(password_update.new_password)
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_password_hash, user_id)
        )
        conn.commit()
        
        return {"message": "Password updated successfully"}

@app.delete("/auth/user")
async def delete_user(user_id: int = Depends(verify_token)):
    """Delete the authenticated user and all their activities"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete user (activities will be deleted due to CASCADE)
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        
        return {"message": "User account and all associated data deleted successfully"}

@app.get("/auth/stats")
async def get_user_stats(user_id: int = Depends(verify_token)):
    """Get user statistics"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Total activities
        cursor.execute(
            "SELECT COUNT(*) as total_activities FROM activities WHERE user_id = %s",
            (user_id,)
        )
        total_activities = cursor.fetchone()['total_activities']
        
        # Total minutes tracked
        cursor.execute(
            "SELECT SUM(duration_minutes) as total_minutes FROM activities WHERE user_id = %s",
            (user_id,)
        )
        total_minutes = cursor.fetchone()['total_minutes'] or 0
        
        # Days with activities
        cursor.execute(
            "SELECT COUNT(DISTINCT activity_date) as active_days FROM activities WHERE user_id = %s",
            (user_id,)
        )
        active_days = cursor.fetchone()['active_days']
        
        # Most tracked category
        cursor.execute(
            """SELECT category, SUM(duration_minutes) as total_minutes 
               FROM activities WHERE user_id = %s 
               GROUP BY category 
               ORDER BY total_minutes DESC 
               LIMIT 1""",
            (user_id,)
        )
        top_category = cursor.fetchone()
        
        return {
            "stats": {
                "total_activities": total_activities,
                "total_minutes_tracked": int(total_minutes),
                "total_hours_tracked": round(total_minutes / 60, 1),
                "active_days": active_days,
                "most_tracked_category": {
                    "category": top_category['category'] if top_category else None,
                    "minutes": int(top_category['total_minutes']) if top_category else 0
                }
            }
        }

# ===== ACTIVITY ENDPOINTS =====

@app.post("/activities", response_model=ActivityResponse)
async def create_activity(activity: ActivityCreate, user_id: int = Depends(verify_token)):
    """Create a new activity entry"""
    activity_date = activity.activity_date or date.today()
    
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """INSERT INTO activities 
               (user_id, category, duration_minutes, notes, mood_rating, photo_url, activity_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, activity.category, activity.duration_minutes, activity.notes,
             activity.mood_rating, activity.photo_url, activity_date)
        )
        activity_id = cursor.lastrowid
        conn.commit()
        
        # Fetch the created activity
        cursor.execute(
            "SELECT * FROM activities WHERE id = %s", (activity_id,)
        )
        created_activity = cursor.fetchone()
        
        return ActivityResponse(
            id=created_activity['id'],
            category=created_activity['category'],
            duration_minutes=created_activity['duration_minutes'],
            notes=created_activity['notes'],
            mood_rating=created_activity['mood_rating'],
            photo_url=created_activity['photo_url'],
            activity_date=created_activity['activity_date'],
            created_at=created_activity['created_at']
        )

@app.get("/activities")
async def get_activities(
    activity_date: Optional[str] = None,
    user_id: int = Depends(verify_token)
):
    """Get activities for a specific date or all activities"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        if activity_date:
            cursor.execute(
                "SELECT * FROM activities WHERE user_id = %s AND activity_date = %s ORDER BY created_at DESC",
                (user_id, activity_date)
            )
        else:
            cursor.execute(
                "SELECT * FROM activities WHERE user_id = %s ORDER BY activity_date DESC, created_at DESC",
                (user_id,)
            )
        
        activities = cursor.fetchall()
        
        return {
            "activities": [
                {
                    "id": activity['id'],
                    "category": activity['category'],
                    "duration_minutes": activity['duration_minutes'],
                    "notes": activity['notes'],
                    "mood_rating": activity['mood_rating'],
                    "photo_url": activity['photo_url'],
                    "activity_date": activity['activity_date'].strftime('%Y-%m-%d') if isinstance(activity['activity_date'], date) else activity['activity_date'],
                    "created_at": activity['created_at'].isoformat() if isinstance(activity['created_at'], datetime) else activity['created_at']
                }
                for activity in activities
            ]
        }

@app.get("/activities/{activity_id}")
async def get_activity(activity_id: int, user_id: int = Depends(verify_token)):
    """Get a specific activity by ID"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM activities WHERE id = %s AND user_id = %s",
            (activity_id, user_id)
        )
        activity = cursor.fetchone()
        
        if not activity:
            raise HTTPException(status_code=404, detail="Activity not found")
        
        return {
            "activity": {
                "id": activity['id'],
                "category": activity['category'],
                "duration_minutes": activity['duration_minutes'],
                "notes": activity['notes'],
                "mood_rating": activity['mood_rating'],
                "photo_url": activity['photo_url'],
                "activity_date": activity['activity_date'].strftime('%Y-%m-%d') if activity['activity_date'] else None,
                "created_at": activity['created_at'].isoformat() if activity['created_at'] else None
            }
        }

@app.put("/activities/{activity_id}")
async def update_activity(
    activity_id: int, 
    activity: ActivityCreate, 
    user_id: int = Depends(verify_token)
):
    """Update an activity"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Check if activity exists and belongs to user
        cursor.execute(
            "SELECT id FROM activities WHERE id = %s AND user_id = %s",
            (activity_id, user_id)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Activity not found")
        
        # Update activity
        cursor.execute(
            """UPDATE activities 
               SET category = %s, duration_minutes = %s, notes = %s, 
                   mood_rating = %s, photo_url = %s, activity_date = %s
               WHERE id = %s AND user_id = %s""",
            (activity.category, activity.duration_minutes, activity.notes,
             activity.mood_rating, activity.photo_url, 
             activity.activity_date or date.today(), activity_id, user_id)
        )
        conn.commit()
        
        # Return updated activity
        cursor.execute(
            "SELECT * FROM activities WHERE id = %s",
            (activity_id,)
        )
        updated_activity = cursor.fetchone()
        
        return {
            "message": "Activity updated successfully",
            "activity": {
                "id": updated_activity['id'],
                "category": updated_activity['category'],
                "duration_minutes": updated_activity['duration_minutes'],
                "notes": updated_activity['notes'],
                "mood_rating": updated_activity['mood_rating'],
                "photo_url": updated_activity['photo_url'],
                "activity_date": updated_activity['activity_date'].strftime('%Y-%m-%d') if updated_activity['activity_date'] else None,
                "created_at": updated_activity['created_at'].isoformat() if updated_activity['created_at'] else None
            }
        }

@app.delete("/activities/{activity_id}")
async def delete_activity(activity_id: int, user_id: int = Depends(verify_token)):
    """Delete an activity"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM activities WHERE id = %s AND user_id = %s",
            (activity_id, user_id)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Activity not found or doesn't belong to user")
        
        conn.commit()
        return {"message": "Activity deleted successfully"}

# ===== BULK OPERATIONS =====

@app.delete("/activities/bulk")
async def delete_multiple_activities(
    activity_ids: List[int], 
    user_id: int = Depends(verify_token)
):
    """Delete multiple activities at once"""
    if not activity_ids:
        raise HTTPException(status_code=400, detail="No activity IDs provided")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create placeholders for the IN clause
        placeholders = ','.join(['%s'] * len(activity_ids))
        query = f"DELETE FROM activities WHERE id IN ({placeholders}) AND user_id = %s"
        
        # Execute delete
        cursor.execute(query, activity_ids + [user_id])
        deleted_count = cursor.rowcount
        conn.commit()
        
        return {
            "message": f"Successfully deleted {deleted_count} activities",
            "deleted_count": deleted_count
        }

@app.delete("/activities/date/{activity_date}")
async def delete_activities_by_date(
    activity_date: str, 
    user_id: int = Depends(verify_token)
):
    """Delete all activities for a specific date"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM activities WHERE activity_date = %s AND user_id = %s",
            (activity_date, user_id)
        )
        deleted_count = cursor.rowcount
        conn.commit()
        
        return {
            "message": f"Successfully deleted {deleted_count} activities for {activity_date}",
            "deleted_count": deleted_count,
            "date": activity_date
        }

# ===== SUMMARY AND ANALYTICS ENDPOINTS =====

@app.get("/summary/{summary_date}")
async def get_daily_summary(summary_date: str, user_id: int = Depends(verify_token)):
    """Get daily summary for a specific date"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT category, SUM(duration_minutes) as total_minutes, 
               COUNT(*) as entry_count, AVG(mood_rating) as avg_mood
               FROM activities 
               WHERE user_id = %s AND activity_date = %s
               GROUP BY category""",
            (user_id, summary_date)
        )
        
        category_data = cursor.fetchall()
        
        # Calculate summary
        total_logged_minutes = sum(row['total_minutes'] for row in category_data)
        categories = {}
        
        for row in category_data:
            categories[row['category']] = {
                "duration_minutes": int(row['total_minutes']),
                "entry_count": row['entry_count'],
                "average_mood": round(float(row['avg_mood']), 1) if row['avg_mood'] else None,
                "percentage": round((int(row['total_minutes']) / total_logged_minutes * 100), 1) if total_logged_minutes > 0 else 0
            }
        
        # Add missing categories
        for category in CATEGORIES:
            if category not in categories:
                categories[category] = {
                    "duration_minutes": 0,
                    "entry_count": 0,
                    "average_mood": None,
                    "percentage": 0
                }
        
        completion_percentage = (len([c for c in categories if categories[c]['duration_minutes'] > 0]) / len(CATEGORIES)) * 100
        
        return DailySummary(
            date=datetime.strptime(summary_date, '%Y-%m-%d').date(),
            total_logged_minutes=total_logged_minutes,
            categories=categories,
            completion_percentage=round(completion_percentage, 1)
        )

@app.get("/trends")
async def get_trends(user_id: int = Depends(verify_token)):
    """Get trend data for all categories"""
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Get data for the last 30 days
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        trends = []
        
        for category in CATEGORIES:
            # Get monthly average
            cursor.execute(
                """SELECT AVG(daily_total) as avg_minutes FROM (
                    SELECT activity_date, SUM(duration_minutes) as daily_total
                    FROM activities 
                    WHERE user_id = %s AND category = %s AND activity_date >= %s
                    GROUP BY activity_date
                ) as daily_totals""",
                (user_id, category, start_date)
            )
            avg_result = cursor.fetchone()
            monthly_avg = round(float(avg_result['avg_minutes']) if avg_result['avg_minutes'] else 0, 1)
            
            # Get last 7 days average
            cursor.execute(
                """SELECT AVG(daily_total) as avg_minutes FROM (
                    SELECT activity_date, SUM(duration_minutes) as daily_total
                    FROM activities 
                    WHERE user_id = %s AND category = %s AND activity_date >= %s
                    GROUP BY activity_date
                ) as daily_totals""",
                (user_id, category, end_date - timedelta(days=7))
            )
            weekly_result = cursor.fetchone()
            weekly_avg = round(float(weekly_result['avg_minutes']) if weekly_result['avg_minutes'] else 0, 1)
            
            # Calculate streak
            cursor.execute(
                """SELECT DISTINCT activity_date FROM activities 
                   WHERE user_id = %s AND category = %s 
                   ORDER BY activity_date DESC""",
                (user_id, category)
            )
            dates = [row['activity_date'].strftime('%Y-%m-%d') if isinstance(row['activity_date'], date) else row['activity_date'] for row in cursor.fetchall()]
            
            streak = 0
            current_date = end_date
            for activity_date in dates:
                if activity_date == current_date.strftime('%Y-%m-%d'):
                    streak += 1
                    current_date -= timedelta(days=1)
                else:
                    break
            
            # Get daily data points for the last 7 days
            cursor.execute(
                """SELECT activity_date, SUM(duration_minutes) as total_minutes
                   FROM activities 
                   WHERE user_id = %s AND category = %s AND activity_date >= %s
                   GROUP BY activity_date
                   ORDER BY activity_date""",
                (user_id, category, end_date - timedelta(days=7))
            )
            data_points = [
                {
                    "date": row['activity_date'].strftime('%Y-%m-%d') if isinstance(row['activity_date'], date) else row['activity_date'], 
                    "minutes": int(row['total_minutes'])
                }
                for row in cursor.fetchall()
            ]
            
            trends.append(TrendData(
                category=category,
                weekly_average=weekly_avg,
                monthly_average=monthly_avg,
                streak_days=streak,
                data_points=data_points
            ))
        
        return {"trends": trends}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

# Alias: to make /login work 
@app.post("/login")
async def login_alias(user: UserLogin):
    return await login(user)


# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
