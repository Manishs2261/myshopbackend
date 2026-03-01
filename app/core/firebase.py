import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException
from app.core.config import settings
import os

_firebase_initialized = False


def init_firebase():
    global _firebase_initialized
    if not _firebase_initialized:
        try:
            if os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)
                _firebase_initialized = True
            else:
                # For development without Firebase
                print("WARNING: Firebase credentials not found. Using mock auth.")
        except Exception as e:
            print(f"Firebase init error: {e}")


def verify_firebase_token(token: str) -> dict:
    """Verify Firebase ID token and return decoded claims."""
    try:
        if not _firebase_initialized:
            # Mock for development - return dummy data
            return {
                "uid": f"mock_uid_{token[:8]}",
                "email": f"user_{token[:8]}@example.com",
                "name": "Test User",
                "phone_number": None,
            }
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {str(e)}")
