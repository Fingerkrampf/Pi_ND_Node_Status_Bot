import hmac
import hashlib
import json

def sign_payload(data: dict, secret_key: str) -> str:
    """
    Signs a dictionary payload with a secret key using HMAC-SHA256.
    Ensures keys are sorted for consistency.
    """
    message = json.dumps(data, sort_keys=True).encode()
    return hmac.new(secret_key.encode(), message, hashlib.sha256).hexdigest()
