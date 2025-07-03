from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import hashlib
import jwt
import os
from contextlib import contextmanager
import json
import re
from fastapi import status
from pydantic import validator

from db import get_db, create_tables
from dotenv import load_dotenv

load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Daily Tracker API", 
    version="1.0.0",
    description="Daily Activity Tracker API deployed on Render"
)

# Mount static files (your HTML frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Security
security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")

# Enable CORS - Update this for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    """Initializes tables in database"""
    try:
        create_tables()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"❌ Error initializing DB: {e}")

# Pydantic models (keeping your existing models)
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

# Predefined categories
CATEGORIES = {
    "Sleep": {"icon": "🛎", "color": "#667eea"},
    "Physical Activity/Exercise": {"icon": "🏃‍♂", "color": "#764ba2"},
    "Nutrition/Meals": {"icon": "🍎", "color": "#f093fb"},
    "Work/Productivity": {"icon": "💼", "color": "#f5576c"},
    "Personal Care/Hygiene": {"icon": "🣜", "color": "#4facfe"},
    "Social/Leisure": {"icon": "🎉", "color": "#00d4aa"},
    "Household Chores/Maintenance": {"icon": "🩹", "color": "#ff6b6b"},
    "Mindfulness/Mental Well-being": {"icon": "🧘‍♀", "color": "#a8e6cf"},
    "Transportation/Commute": {"icon": "🚗", "color": "#ffd93d"},
    "Learning/Skill Development": {"icon": "📚", "color": "#6c5ce7"}
}

# Utility functions
def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = os.getenv("PASSWORD_SALT", "daily_tracker_salt")
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
    """Verify JWT token and return user_id"""
    try:
        if not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_id

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()

@app.get("/")
async def serve_frontend():
    """Serve the main HTML file"""
    return FileResponse('static/index.html', media_type='text/html')

@app.get("/api")
async def root():
    return {
        "message": "Daily Tracker API is running on Render", 
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
        return {
            "status": "healthy", 
            "database": "connected", 
            "timestamp": datetime.utcnow().isoformat(),
            "environment": "production"
        }
    except Exception as e:
        return {
            "status": "unhealthy", 
            "database": "disconnected", 
            "error": str(e), 
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/categories")
async def get_categories():
    """Get all available categories"""
    return {"categories": CATEGORIES}

# Authentication endpoints
@app.post("/auth/register")
async def register(user: UserCreate):
    ...

@app.post("/signup")
async def signup_redirect(user: UserCreate):
    """Alias /signup to /auth/register"""
    return await register(user)

@app.post("/auth/login")
async def login(user: UserLogin):
    ...

@app.post("/activities")
async def create_activity(activity: ActivityCreate, user_id: int = Depends(verify_token)):
    ...

@app.get("/activities")
async def get_activities(
    activity_date: Optional[str] = None,
    user_id: int = Depends(verify_token)
):
    ...

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Render uses PORT environment variable
    uvicorn.run("main:app", host="0.0.0.0", port=port)
