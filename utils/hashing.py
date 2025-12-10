from passlib.context import CryptContext

# CLEAN bcrypt context — NO EXTRA OPTIONS
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

def hash_password(password: str) -> str:
    password = password[:70]  # manual safe truncation
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    plain = plain[:70]
    return pwd_context.verify(plain, hashed)
