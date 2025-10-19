from passlib.hash import bcrypt

def hash_answer_key(value: str):
    if not value:
        return None
    return bcrypt.hash(value)

def verify_answer_key(value: str, hashed: str):
    try:
        return bcrypt.verify(value, hashed)
    except Exception:
        return False