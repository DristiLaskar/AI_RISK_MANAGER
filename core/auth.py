import sqlite3
import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "users.db"
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            token TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100000
    ).hex()


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/signup")
def signup(data: SignupRequest):

    if "@" not in data.email or "." not in data.email:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    if len(data.name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name is required.")

    conn = get_db()

    existing = conn.execute(
        "SELECT id FROM users WHERE email = ?", (data.email.lower(),)
    ).fetchone()

    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    salt = secrets.token_hex(16)
    password_hash = hash_password(data.password, salt)
    token = secrets.token_hex(32)

    conn.execute(
        "INSERT INTO users (name, email, password_hash, salt, token) VALUES (?, ?, ?, ?, ?)",
        (data.name.strip(), data.email.lower(), password_hash, salt, token)
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "token": token, "name": data.name.strip(), "email": data.email.lower()}


@router.post("/auth/login")
def login(data: LoginRequest):
    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (data.email.lower(),)
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    attempted_hash = hash_password(data.password, user["salt"])

    if not hmac.compare_digest(attempted_hash, user["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = secrets.token_hex(32)
    conn.execute("UPDATE users SET token = ? WHERE id = ?", (token, user["id"]))
    conn.commit()
    conn.close()

    return {"status": "ok", "token": token, "name": user["name"], "email": user["email"]}


@router.get("/auth/me")
def get_me(token: str):
    conn = get_db()

    user = conn.execute(
        "SELECT name, email FROM users WHERE token = ?", (token,)
    ).fetchone()

    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Not logged in.")

    return {"name": user["name"], "email": user["email"]}