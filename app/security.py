from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings

# Argon2id (paramètres par défaut de argon2-cffi : time_cost=3, memory_cost=64Mo,
# parallelism=4) — recommandé par l'OWASP, remplace passlib/bcrypt.
password_hasher = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(plain_password: str) -> str:
    """Utilitaire pour générer le hash à mettre dans API_PASSWORD_HASH.

    À lancer une fois en local :
        python -c "from app.security import hash_password; print(hash_password('mon_mdp'))"
    """
    return password_hasher.hash(plain_password)


def verify_credentials(username: str, password: str) -> bool:
    if username != settings.api_username:
        return False
    try:
        password_hasher.verify(settings.api_password_hash, password)
    except VerifyMismatchError:
        return False
    return True


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_current_subject(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        return subject
    except JWTError:
        raise credentials_exception
