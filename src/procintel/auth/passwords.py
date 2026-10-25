"""Password hashes: scrypt with a random salt per password (standard library, no extra package)."""
from __future__ import annotations

import hashlib
import hmac
import os

N, R, P = 2 ** 14, 8, 1  # scrypt cost: about 50 ms per check, so guessing is slow and logging in is not
MIN_LENGTH = 10


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), digest)


def check_strength(password: str) -> str | None:
    """A problem with a new password, or None."""
    if len(password) < MIN_LENGTH:
        return f"at least {MIN_LENGTH} characters"
    return None
