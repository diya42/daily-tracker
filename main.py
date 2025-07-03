from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional
from datetime import datetime, date, timedelta
import hashlib
import jwt
import os
import re
from fastapi import status
from db import get_db, create_tables
from dotenv import load_dotenv

load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Daily Tracker API",
    version="1.0.0",
    description="Daily Activity Tracker API deployed on Render"
)

# Mount static files (HTML frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Security
security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    create_tables()
    print("✅ Database initialized successfully.")

# Utility functions
def hash_password(password: str) -> str:
    salt = os.getenv("PASSWORD_SALT", "daily_tracker_salt")
    return hashlib.sha256((password + salt).encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def create_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=30),
        "iat": datetime.utcnow(),
        "type": "access_token"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("user_id")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None

    @validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r'[A-Za-z]', v) or not re.search(r'\d', v):
            raise ValueError("Password must contain letters and numbers")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ActivityCreate(BaseModel):
    category: str
    duration_minutes: int
    notes: Optional[str] = None
    mood_rating: Optional[int] = None
    photo_url: Optional[str] = None
    activity_date: Optional[date] = None

# Serve index.html
@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

# Health check
@app.get("/health")
async def health_check():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
        return {"status": "healthy", "db": "connected"}
    except:
        return {"status": "unhealthy", "db": "disconnected"}

# --- Auth Endpoints ---

@app.post("/auth/register")
async def register(user: UserCreate):
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email.lower(),))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        password_hash = hash_password(user.password)
        cursor.execute(
            """INSERT INTO users (email, password_hash, name, age, gender, is_active, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user.email.lower(), password_hash, user.name, user.age, user.gender, True, datetime.utcnow())
        )
        conn.commit()
        user_id = cursor.lastrowid
        token = create_token(user_id)

        return {"message": "User registered", "token": token, "user": {"id": user_id, "email": user.email}}

@app.post("/auth/login")
async def login(user: UserLogin):
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, password_hash, name FROM users WHERE email = %s", (user.email.lower(),))
        db_user = cursor.fetchone()

        if not db_user or not verify_password(user.password, db_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_token(db_user["id"])
        return {"message": "Login successful", "token": token, "user": {"id": db_user["id"], "email": user.email}}

# Aliases expected by frontend
@app.post("/signup")
async def signup_alias(user: UserCreate):
    return await register(user)

@app.post("/login")
async def login_alias(user: UserLogin):
    return await login(user)

# --- Activities ---

@app.post("/activities")
async def create_activity(activity: ActivityCreate, user_id: int = Depends(verify_token)):
    activity_date = activity.activity_date or date.today()
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """INSERT INTO activities (user_id, category, duration_minutes, notes, mood_rating, photo_url, activity_date, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, activity.category, activity.duration_minutes, activity.notes, activity.mood_rating,
             activity.photo_url, activity_date, datetime.utcnow())
        )
        conn.commit()
        return {"message": "Activity added"}

@app.get("/activities")
async def get_activities(user_id: int = Depends(verify_token)):
    with get_db() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM activities WHERE user_id = %s ORDER BY activity_date DESC", (user_id,))
        return {"activities": cursor.fetchall()}
