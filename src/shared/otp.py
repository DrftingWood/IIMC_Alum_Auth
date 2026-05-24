import secrets

import bcrypt

from src.shared.config import get_settings


def generate_code() -> str:
    """Return a uniformly-random 6-digit string, zero-padded."""
    return f"{secrets.randbelow(10**6):06d}"


def hash_code(code: str) -> str:
    pepper = get_settings().otp_pepper
    salted = (code + pepper).encode()
    return bcrypt.hashpw(salted, bcrypt.gensalt(rounds=12)).decode()


def verify_code(code: str, hashed: str) -> bool:
    pepper = get_settings().otp_pepper
    salted = (code + pepper).encode()
    try:
        return bcrypt.checkpw(salted, hashed.encode())
    except ValueError:
        return False
