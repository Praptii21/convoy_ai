from fastapi import APIRouter, HTTPException
from backend.db_connection import get_connection
from backend.utils.hashing import hash_password, verify_password
from backend.utils.auth_utils import create_access_token
from datetime import timedelta
import re
import random
import time

router = APIRouter()

# In-memory OTP store
otp_store = {}  
# Structure:
# otp_store[email] = { "otp": "123456", "expires_at": 1730000000 }


# -------------------------
# VALIDATION HELPERS
# -------------------------

EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"

def is_valid_email(email: str) -> bool:
    return re.match(EMAIL_REGEX, email) is not None



def validate_phone(phone: str):
    # Indian 10-digit
    pattern = r"^[6-9]\d{9}$"
    return re.match(pattern, phone)


def generate_otp():
    return str(random.randint(100000, 999999))



# --------------------------
# STEP 1: REGISTER → SEND OTP
# --------------------------

@router.post("/register/send-otp")
def register_send_otp(data: dict):
    email = data.get("email")
    phone = data.get("phone_number")

    if not email or not phone:
        raise HTTPException(status_code=400, detail="Email & phone required")

    if not validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    if not validate_phone(phone):
        raise HTTPException(status_code=400, detail="Invalid phone number format (must be 10 digits starting with 6-9)")

    # Generate OTP
    otp = generate_otp()
    otp_store[email] = {
        "otp": otp,
        "expires_at": time.time() + 300  # 5 minutes
    }

    return {
        "message": "OTP sent successfully",
        "email": email,
        "otp": otp   # Showing in JSON (as requested)
    }



# --------------------------
# STEP 2: REGISTER → VERIFY OTP
# --------------------------

@router.post("/register/verify-otp")
def register_verify_otp(data: dict):
    email = data.get("email")
    otp = data.get("otp")

    if email not in otp_store:
        raise HTTPException(status_code=400, detail="OTP not requested")

    record = otp_store[email]

    if time.time() > record["expires_at"]:
        raise HTTPException(status_code=400, detail="OTP expired")

    if otp != record["otp"]:
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    return {"message": "OTP verified successfully"}



# --------------------------
# STEP 3: REGISTER → COMPLETE
# --------------------------

@router.post("/register/complete")
def register_user(data: dict):
    name = data.get("name")
    email = data.get("email")
    phone_number = data.get("phone_number")
    password = data.get("password")

    # Must verify OTP first
    if email not in otp_store:
        raise HTTPException(status_code=400, detail="OTP not verified")

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

        # Create token
        token = create_access_token(
            data={"user_id": user_id, "email": email},
            expires_delta=timedelta(days=1)
        )

        # OTP no longer needed
        del otp_store[email]

        return {
            "message": "Registration successful",
            "user_id": user_id,
            "access_token": token,
            "token_type": "bearer"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    finally:
        conn.close()




# --------------------------
# LOGIN → SEND OTP
# --------------------------

@router.post("/login/send-otp")
def login_send_otp(data: dict):
    email = data.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    if not validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM users WHERE email=%s", (email,))
    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create OTP
    otp = generate_otp()
    otp_store[email] = {
        "otp": otp,
        "expires_at": time.time() + 300
    }

    return {
        "message": "OTP sent for login",
        "otp": otp
    }



# --------------------------
# LOGIN → VERIFY OTP & LOGIN
# --------------------------

@router.post("/login/verify-otp")
def login_verify_otp(data: dict):
    email = data.get("email")
    password = data.get("password")
    otp = data.get("otp")

    if not all([email, password, otp]):
        raise HTTPException(status_code=400, detail="Email, password & OTP are required")

    # OTP validation
    if email not in otp_store:
        raise HTTPException(status_code=400, detail="OTP not requested")

    record = otp_store[email]
    if time.time() > record["expires_at"]:
        raise HTTPException(status_code=400, detail="OTP expired")

    if otp != record["otp"]:
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    # Validate user credentials
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT user_id, password_hash FROM users WHERE email=%s;", (email,))
    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect password")

    # Create token
    token = create_access_token(
        data={"user_id": user["user_id"], "email": email},
        expires_delta=timedelta(days=1)
    )

    # OTP done
    del otp_store[email]

    return {
        "message": "Login successful",
        "user_id": user["user_id"],
        "access_token": token,
        "token_type": "bearer"
    }
