"""Supabase email/password authentication helpers."""
from supabase import create_client
from config import settings

def get_auth_client():
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY in backend/.env")
    return create_client(settings.supabase_url, settings.supabase_publishable_key)

def sign_up_user(email: str, password: str):
    return get_auth_client().auth.sign_up({"email": email, "password": password})

def sign_in_user(email: str, password: str):
    return get_auth_client().auth.sign_in_with_password({"email": email, "password": password})

def request_password_reset(email: str):
    return get_auth_client().auth.reset_password_email(email)

def verify_access_token(access_token: str):
    """Ask Supabase Auth to validate the token; never trust a user ID from the client."""
    response = get_auth_client().auth.get_user(access_token)
    user = getattr(response, "user", None)
    if user is None:
        raise ValueError("Invalid or expired session")
    return {"id": str(user.id), "email": user.email}
