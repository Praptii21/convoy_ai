from fastapi import APIRouter, HTTPException
from backend.db_connection import get_connection
from backend.utils.hashing import hash_password, verify_password

router = APIRouter()

# ------------------ REGISTER ------------------

@router.post("/register")
def register_user(data: dict):
    name = data.get("name")
    email = data.get("email")
    phone_number = data.get("phone_number")
    password = data.get("password")

    if not all([name, email, phone_number, password]):
        raise HTTPException(status_code=400, detail="All fields required")

    hashed = hash_password(password)

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO users (name, email, phone_number, password_hash, role)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING user_id;
        """, (name, email, phone_number, hashed, "officer"))

        user_id = cur.fetchone()["user_id"]
        conn.commit()

        return {"message": "Registration successful", "user_id": user_id}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    finally:
        conn.close()


# ------------------ LOGIN ------------------

@router.post("/login")
def login_user(data: dict):
    email = data.get("email")
    password = data.get("password")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id, password_hash FROM users WHERE email=%s;", (email,))
    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_id = user["user_id"]
    hashed_pw = user["password_hash"]

    if not verify_password(password, hashed_pw):
        raise HTTPException(status_code=401, detail="Incorrect password")

    return {"message": "Login successful", "user_id": user_id}
