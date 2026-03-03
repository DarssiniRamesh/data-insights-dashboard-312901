c"""
Database module for SQLite connection and initialization.

Key design goals for preview/runtime robustness:
- App must boot even if SQLITE_DB_PATH is missing/invalid/unwritable.
- Default DB path must be deterministic and writable relative to container root.
- Provide a lightweight readiness check that can touch DB.
"""
import logging
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("backend_api.db")

_connection: Optional[sqlite3.Connection] = None
_db_degraded_mode: bool = False
_db_effective_path: Optional[str] = None
_db_initialized: bool = False


def _default_db_path() -> str:
    """
    Compute a deterministic default DB path under the backend_api container root.

    We avoid relying on process working directory (which can differ between
    pytest, uvicorn, and preview environments).
    """
    # __file__ = .../backend_api/src/database/__init__.py
    # parents[2] = .../backend_api
    container_root = Path(__file__).resolve().parents[2]
    return str(container_root / "data" / "app.db")


def _fallback_db_path() -> str:
    """Return a writable fallback path in /tmp."""
    return str(Path(tempfile.gettempdir()) / "backend_api" / "app.db")


def _connect_sqlite(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection and enforce baseline pragmas."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_parent_dir(db_path: str) -> None:
    """Ensure the parent directory exists for db_path."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _ensure_system_user(conn: sqlite3.Connection) -> None:
    """
    Ensure a deterministic 'system' user exists.

    This user is required because audit_events.actor_user_id has a foreign key
    constraint to users(user_id), and several services/compat endpoints emit
    system-initiated audit events with actor_user_id='system'.

    The function is idempotent and commits immediately so subsequent audit writes
    won't fail with FK violations.

    Important: This function must not crash if called before the `users` table exists.
    """
    # Import locally to avoid import cycles at module import time.
    # Support both import roots: services.auth (pythonpath=src) and src.services.auth (package import)
    try:
        from services.auth import AuthService
    except ImportError:  # pragma: no cover
        from ..services.auth import AuthService

    try:
        cursor = conn.execute(
            "SELECT user_id, username, roles, is_active FROM users WHERE user_id = ?",
            ("system",),
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users);").fetchall()}
    except sqlite3.OperationalError:
        # users table not created yet. init_db() will call us again after table creation.
        logger.warning("Cannot ensure system user because users table does not exist yet.")
        return

    # If critical auth columns are missing in an older schema, skip instead of crashing.
    required_cols = {"user_id", "username", "password_hash", "password_salt", "roles", "is_active", "created_at"}
    if not required_cols.issubset(cols):
        logger.warning("users table missing required columns (%s); cannot ensure system user safely.", sorted(required_cols - cols))
        return

    row = cursor.fetchone()

    desired_roles = "system,admin"  # includes 'admin' per requirements; 'system' is informational for DB only
    desired_primary_role = "admin"
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    if row:
        # Best-effort normalization to ensure it's active and has admin.
        roles = (row["roles"] or "").split(",") if row["roles"] else []
        if "admin" not in roles:
            roles.append("admin")
        if "system" not in roles:
            roles.append("system")
        roles_str = ",".join([r for r in roles if r])

        updates = {
            "username": "system",
            "roles": roles_str,
            "is_active": 1,
        }
        if "role" in cols:
            updates["role"] = desired_primary_role
        if "display_name" in cols:
            updates["display_name"] = "System"

        set_sql = ", ".join([f"{k} = ?" for k in updates.keys()])
        conn.execute(f"UPDATE users SET {set_sql} WHERE user_id = ?", (*updates.values(), "system"))
        conn.commit()
        return

    # Create required password fields; password isn't used for system actions but schema requires it.
    auth = AuthService(conn)
    pwd_hash, salt = auth.hash_password("Passw0rd!")

    insert_cols = ["user_id", "username", "password_hash", "password_salt", "roles", "is_active", "created_at"]
    insert_vals = ["system", "system", pwd_hash, salt, desired_roles, True, created_at]

    if "display_name" in cols:
        insert_cols.append("display_name")
        insert_vals.append("System")
    if "role" in cols:
        insert_cols.append("role")
        insert_vals.append(desired_primary_role)

    placeholders = ",".join(["?"] * len(insert_cols))
    conn.execute(
        f"INSERT INTO users({','.join(insert_cols)}) VALUES({placeholders})",
        insert_vals,
    )
    conn.commit()


# PUBLIC_INTERFACE
def get_db_path() -> str:
    """Get the SQLite database path from environment or use a safe default."""
    db_path = os.getenv("SQLITE_DB_PATH", "").strip()
    if not db_path:
        db_path = _default_db_path()

    # If user configured a relative path (e.g., "data/app.db"), resolve it against
    # the backend_api root to avoid surprises when cwd differs.
    if db_path != ":memory:" and not Path(db_path).is_absolute() and not db_path.startswith("file:"):
        base_dir = Path(__file__).resolve().parents[2]  # .../backend_api
        db_path = str(base_dir / db_path)

    # Create parent dir so sqlite can create/open the file cleanly.
    # If this fails, caller may choose to fallback to /tmp or in-memory.
    try:
        _ensure_parent_dir(db_path)
    except Exception:
        logger.exception("Failed to create parent directory for SQLITE_DB_PATH=%s", db_path)

    return db_path


# PUBLIC_INTERFACE
def get_connection() -> sqlite3.Connection:
    """
    Get or create SQLite connection with foreign keys enabled.

    Contract:
      - Returns: a SQLite connection with row_factory configured.
      - Side effects: may create DB file/dirs; will initialize schema once per process.
      - Errors: never raises due to DB path issues; will fallback to /tmp or in-memory.

    Why this exists:
      Preview/runtime environments can have differing working directories and FS
      permissions. If we silently fall back to a different DB (e.g. /tmp or :memory:)
      without initializing schema/users, authentication will consistently return 401
      due to "user not found". We therefore ensure schema + baseline seed users are
      present for *any* opened connection.
    """
    global _connection, _db_degraded_mode, _db_effective_path, _db_initialized

    if _connection is not None:
        return _connection

    primary_path: Optional[str] = None

    # First attempt: env/default path
    try:
        primary_path = get_db_path()
        _connection = _connect_sqlite(primary_path)
        _db_effective_path = primary_path
        _db_degraded_mode = False
    except Exception:
        logger.exception("Failed opening SQLite DB at path=%s", primary_path)

    # Second attempt: writable /tmp location (still persistent within container FS)
    if _connection is None:
        fallback_path: Optional[str] = None
        try:
            fallback_path = _fallback_db_path()
            _ensure_parent_dir(fallback_path)
            _connection = _connect_sqlite(fallback_path)
            _db_effective_path = fallback_path
            _db_degraded_mode = True
            logger.warning("DB running in degraded mode using fallback path=%s", fallback_path)
        except Exception:
            logger.exception("Failed opening SQLite DB fallback path=%s", fallback_path)

    # Final attempt: in-memory
    if _connection is None:
        _connection = _connect_sqlite(":memory:")
        _db_effective_path = ":memory:"
        _db_degraded_mode = True
        logger.warning("DB running in degraded mode using in-memory SQLite.")

    # Initialize schema exactly once per process (idempotent but keep it explicit)
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
            logger.info("DB initialized (path=%s degraded=%s)", _db_effective_path, _db_degraded_mode)
        except Exception:
            # Do not crash startup; API can still serve health/readiness.
            logger.exception("Non-fatal: DB initialization failed (path=%s).", _db_effective_path)

    return _connection


# PUBLIC_INTERFACE
def close_connection() -> None:
    """Close the database connection (if any)."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None


# PUBLIC_INTERFACE
def db_status() -> Tuple[bool, str, bool]:
    """
    Return (ok, path, degraded_mode) without raising.

    ok=True means a connection can be created and a trivial query succeeds.
    """
    try:
        conn = get_connection()
        conn.execute("SELECT 1;")
        return True, _db_effective_path or "", _db_degraded_mode
    except Exception:
        logger.exception("DB status check failed.")
        return False, _db_effective_path or "", True


# PUBLIC_INTERFACE
def init_db() -> None:
    """Initialize database schema.

    Notes:
      - This function is idempotent and safe to call multiple times.
      - It ensures baseline users exist so that login can succeed in preview/dev
        environments even if the DB file had to be created (e.g., after falling
        back to /tmp or :memory:).
    """
    conn = get_connection()

    # Users table with authentication fields
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        password_salt TEXT NOT NULL,
        roles TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        display_name TEXT,
        role TEXT
    );
    """
    )

    # Create index on username for fast lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")

    # Forward-compatible migration for older DBs: add optional columns if missing.
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users);").fetchall()}
        if "display_name" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT;")
        if "role" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT;")
    except Exception:
        # Never fail startup due to a best-effort migration.
        logger.exception("Non-fatal: failed applying users table forward-compat migrations.")

    # Ensure deterministic system user exists before any audit events can be written.
    _ensure_system_user(conn)

    # Seed baseline dev/test users (idempotent; skips if already present).
    # This prevents confusing persistent 401s in environments where the DB had to
    # be created or was empty.
    try:
        seed_test_users()
    except Exception:
        logger.exception("Non-fatal: failed seeding baseline users.")

    # Drafts table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS drafts (
        draft_id TEXT PRIMARY KEY,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('draft')),
        package_json TEXT NOT NULL,
        created_by_user_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        FOREIGN KEY(created_by_user_id) REFERENCES users(user_id)
    );
    """
    )

    # Data assets table (formerly submissions)
    # Metadata constrained to: title (required, 1-200 chars), description (optional, max 2000 chars), owner (required, 1-120 chars)
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS data_assets (
        data_asset_id TEXT PRIMARY KEY,
        draft_id TEXT NOT NULL,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        title TEXT NOT NULL CHECK (length(title) >= 1 AND length(title) <= 200),
        description TEXT CHECK (length(description) <= 2000),
        owner TEXT NOT NULL CHECK (length(owner) >= 1 AND length(owner) <= 120),
        state TEXT NOT NULL CHECK (state IN ('validating','failed_validation','in_review','remediating','approved','published','rejected')),
        submitter_user_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        last_updated_at_utc TEXT NOT NULL,
        active_deviation_id TEXT,
        FOREIGN KEY(draft_id) REFERENCES drafts(draft_id),
        FOREIGN KEY(submitter_user_id) REFERENCES users(user_id)
    );
    """
    )

    # Legacy submissions table for backward compatibility (view or empty table)
    # This allows old code/tests referencing 'submissions' to continue working temporarily
    conn.execute(
        """
    CREATE VIEW IF NOT EXISTS submissions AS
    SELECT 
        data_asset_id AS submission_id,
        draft_id,
        package_id,
        package_version,
        state,
        submitter_user_id,
        created_at_utc,
        last_updated_at_utc,
        active_deviation_id
    FROM data_assets;
    """
    )

    # Pipeline jobs table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS pipeline_jobs (
        pipeline_job_id TEXT PRIMARY KEY,
        data_asset_id TEXT NOT NULL,
        job_type TEXT NOT NULL CHECK (job_type IN ('validate','publish','monitor')),
        state TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed')),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error_code TEXT,
        last_error_message TEXT,
        created_at_utc TEXT NOT NULL,
        started_at_utc TEXT,
        finished_at_utc TEXT,
        FOREIGN KEY(data_asset_id) REFERENCES data_assets(data_asset_id)
    );
    """
    )

    # Artifacts table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        artifact_type TEXT NOT NULL CHECK (artifact_type IN ('validation_report','evidence_manifest','approval_record','audit_excerpt','deviation_record')),
        content_type TEXT NOT NULL,
        storage_ref TEXT NOT NULL,
        hash_sha256 TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    );
    """
    )

    # Validation runs table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS validation_runs (
        validation_run_id TEXT PRIMARY KEY,
        data_asset_id TEXT NOT NULL,
        validation_profile TEXT NOT NULL,
        overall_status TEXT NOT NULL CHECK (overall_status IN ('pass','fail')),
        checks_json TEXT NOT NULL,
        rule_versions_json TEXT,
        report_artifact_id TEXT NOT NULL,
        report_hash_sha256 TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(data_asset_id) REFERENCES data_assets(data_asset_id),
        FOREIGN KEY(report_artifact_id) REFERENCES artifacts(artifact_id)
    );
    """
    )

    # Review logs table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS review_logs (
        review_log_id TEXT PRIMARY KEY,
        data_asset_id TEXT NOT NULL,
        reviewer_user_id TEXT NOT NULL,
        notes TEXT,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(data_asset_id) REFERENCES data_assets(data_asset_id),
        FOREIGN KEY(reviewer_user_id) REFERENCES users(user_id)
    );
    """
    )

    # Approval records table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS approval_records (
        approval_record_id TEXT PRIMARY KEY,
        data_asset_id TEXT NOT NULL,
        decision TEXT NOT NULL CHECK (decision IN ('publish','reject')),
        approver_user_id TEXT NOT NULL,
        signature_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(data_asset_id) REFERENCES data_assets(data_asset_id),
        FOREIGN KEY(approver_user_id) REFERENCES users(user_id)
    );
    """
    )

    # Deviations table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS deviations (
        deviation_id TEXT PRIMARY KEY,
        data_asset_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('requested','pending_secondary_approval','approved','rejected','expired')),
        justification TEXT NOT NULL,
        capa_plan TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL,
        requested_by_user_id TEXT NOT NULL,
        requested_signature_json TEXT NOT NULL,
        secondary_approver_user_id TEXT,
        secondary_signature_json TEXT,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        FOREIGN KEY(data_asset_id) REFERENCES data_assets(data_asset_id),
        FOREIGN KEY(requested_by_user_id) REFERENCES users(user_id),
        FOREIGN KEY(secondary_approver_user_id) REFERENCES users(user_id)
    );
    """
    )

    # Evidence packages table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS evidence_packages (
        evidence_package_id TEXT PRIMARY KEY,
        data_asset_id TEXT NOT NULL,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        minted_identifier TEXT NOT NULL,
        manifest_artifact_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(data_asset_id) REFERENCES data_assets(data_asset_id),
        FOREIGN KEY(manifest_artifact_id) REFERENCES artifacts(artifact_id)
    );
    """
    )

    # Audit events table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS audit_events (
        audit_event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        actor_user_id TEXT NOT NULL,
        actor_role TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        result TEXT NOT NULL CHECK (result IN ('success','failure','blocked')),
        details_json TEXT,
        FOREIGN KEY(actor_user_id) REFERENCES users(user_id)
    );
    """
    )

    # Monitoring events table
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS monitoring_events (
        monitoring_event_id TEXT PRIMARY KEY,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK (event_type IN ('freshness_check','freshness_breach')),
        status TEXT NOT NULL CHECK (status IN ('ok','breach')),
        details_json TEXT,
        created_at_utc TEXT NOT NULL
    );
    """
    )

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_assets_package ON data_assets(package_id, package_version);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_assets_state ON data_assets(state);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_validation_runs_data_asset ON validation_runs(data_asset_id, created_at_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_data_asset ON pipeline_jobs(data_asset_id, created_at_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(entity_type, entity_id, timestamp_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_packages_data_asset ON evidence_packages(data_asset_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_events_package ON monitoring_events(package_id, package_version, created_at_utc);")

    conn.commit()


# PUBLIC_INTERFACE
def seed_test_users() -> None:
    """Seed test users for development and testing with authentication."""
    conn = get_connection()

    # Ensure system user is always present (audit FK safety).
    _ensure_system_user(conn)

    # Import auth service for password hashing (support both import roots)
    try:
        from services.auth import AuthService
    except ImportError:  # pragma: no cover
        from ..services.auth import AuthService

    auth_service = AuthService(conn)

    # Seed users with default password "Passw0rd!"
    test_users = [
        ("submitter1", "Passw0rd!", ["submitter"], "Submitter User"),
        ("reviewer1", "Passw0rd!", ["reviewer"], "Reviewer User"),
        ("approver1", "Passw0rd!", ["approver"], "Approver User"),
        ("auditor1", "Passw0rd!", ["auditor"], "Auditor User"),
        ("admin1", "Passw0rd!", ["admin"], "Admin User"),
        ("multi_role", "Passw0rd!", ["submitter", "reviewer"], "Multi-Role User"),
    ]

    for username, password, roles, display_name in test_users:
        try:
            # Check if user exists
            cursor = conn.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                continue

            # Hash password
            pwd_hash, salt = auth_service.hash_password(password)

            # Generate user ID
            import uuid

            user_id = f"u-{str(uuid.uuid4())[:8]}"
            created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            roles_str = ",".join(roles)

            # For backward compatibility, set role to first role
            primary_role = roles[0] if roles else "submitter"

            # Insert user
            conn.execute(
                """INSERT INTO users(user_id, username, password_hash, password_salt, roles, is_active, created_at, display_name, role)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (user_id, username, pwd_hash, salt, roles_str, True, created_at, display_name, primary_role),
            )
        except sqlite3.IntegrityError:
            pass

    conn.commit()
