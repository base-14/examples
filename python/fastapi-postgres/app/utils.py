from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

pwd_context = PasswordHash((BcryptHasher(),))


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)
