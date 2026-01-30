"""
Utility functions for the backend API.
"""
import uuid
import json
import hashlib
from datetime import datetime, UTC
from typing import Any, Dict


def generate_id(prefix: str = "") -> str:
    """Generate a unique identifier."""
    uid = str(uuid.uuid4())
    return f"{prefix}-{uid}" if prefix else uid


def utc_now_iso() -> str:
    """Get current UTC timestamp in ISO-8601 format with trailing 'Z'."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(data: Any) -> str:
    """Serialize data to canonical JSON (sorted keys, no whitespace)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_hash(data: Any) -> str:
    """Compute SHA-256 hash of data."""
    if isinstance(data, str):
        content = data.encode("utf-8")
    elif isinstance(data, (dict, list)):
        content = canonical_json(data).encode("utf-8")
    else:
        content = str(data).encode("utf-8")

    return hashlib.sha256(content).hexdigest()


def make_error_response(code: str, message: str, correlation_id: str, details: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create a standard error response."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "correlation_id": correlation_id,
            "timestamp_utc": utc_now_iso(),
        }
    }
