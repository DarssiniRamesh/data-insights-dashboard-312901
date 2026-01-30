"""
Database module for SQLite connection and initialization.
"""
import sqlite3
from pathlib import Path
from typing import Optional
import os
from datetime import datetime, timezone

_connection: Optional[sqlite3.Connection] = None


def get_db_path() -> str:
    """Get the SQLite database path from environment or use default."""
    db_path = os.getenv("SQLITE_DB_PATH", "data/app.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection() -> sqlite3.Connection:
    """Get or create SQLite connection with foreign keys enabled."""
    global _connection
    if _connection is None:
        db_path = get_db_path()
        _connection = sqlite3.connect(db_path, check_same_thread=False)
        _connection.execute("PRAGMA foreign_keys = ON;")
        _connection.row_factory = sqlite3.Row
    return _connection


def close_connection():
    """Close the database connection."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None


def init_db():
    """Initialize database schema."""
    conn = get_connection()
    
    # Users table with authentication fields
    conn.execute("""
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
    """)
    
    # Create index on username for fast lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
    
    # Drafts table
    conn.execute("""
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
    """)
    
    # Submissions table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        submission_id TEXT PRIMARY KEY,
        draft_id TEXT NOT NULL,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('validating','failed_validation','in_review','remediating','approved','published','rejected')),
        submitter_user_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        last_updated_at_utc TEXT NOT NULL,
        active_deviation_id TEXT,
        FOREIGN KEY(draft_id) REFERENCES drafts(draft_id),
        FOREIGN KEY(submitter_user_id) REFERENCES users(user_id)
    );
    """)
    
    # Pipeline jobs table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_jobs (
        pipeline_job_id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
        job_type TEXT NOT NULL CHECK (job_type IN ('validate','publish','monitor')),
        state TEXT NOT NULL CHECK (state IN ('queued','running','succeeded','failed')),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error_code TEXT,
        last_error_message TEXT,
        created_at_utc TEXT NOT NULL,
        started_at_utc TEXT,
        finished_at_utc TEXT,
        FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
    );
    """)
    
    # Artifacts table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        artifact_type TEXT NOT NULL CHECK (artifact_type IN ('validation_report','evidence_manifest','approval_record','audit_excerpt','deviation_record')),
        content_type TEXT NOT NULL,
        storage_ref TEXT NOT NULL,
        hash_sha256 TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    );
    """)
    
    # Validation runs table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS validation_runs (
        validation_run_id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
        validation_profile TEXT NOT NULL,
        overall_status TEXT NOT NULL CHECK (overall_status IN ('pass','fail')),
        checks_json TEXT NOT NULL,
        rule_versions_json TEXT,
        report_artifact_id TEXT NOT NULL,
        report_hash_sha256 TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(submission_id) REFERENCES submissions(submission_id),
        FOREIGN KEY(report_artifact_id) REFERENCES artifacts(artifact_id)
    );
    """)
    
    # Review logs table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS review_logs (
        review_log_id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
        reviewer_user_id TEXT NOT NULL,
        notes TEXT,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(submission_id) REFERENCES submissions(submission_id),
        FOREIGN KEY(reviewer_user_id) REFERENCES users(user_id)
    );
    """)
    
    # Approval records table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS approval_records (
        approval_record_id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
        decision TEXT NOT NULL CHECK (decision IN ('publish','reject')),
        approver_user_id TEXT NOT NULL,
        signature_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(submission_id) REFERENCES submissions(submission_id),
        FOREIGN KEY(approver_user_id) REFERENCES users(user_id)
    );
    """)
    
    # Deviations table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS deviations (
        deviation_id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
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
        FOREIGN KEY(submission_id) REFERENCES submissions(submission_id),
        FOREIGN KEY(requested_by_user_id) REFERENCES users(user_id),
        FOREIGN KEY(secondary_approver_user_id) REFERENCES users(user_id)
    );
    """)
    
    # Evidence packages table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS evidence_packages (
        evidence_package_id TEXT PRIMARY KEY,
        submission_id TEXT NOT NULL,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        minted_identifier TEXT NOT NULL,
        manifest_artifact_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(submission_id) REFERENCES submissions(submission_id),
        FOREIGN KEY(manifest_artifact_id) REFERENCES artifacts(artifact_id)
    );
    """)
    
    # Audit events table
    conn.execute("""
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
    """)
    
    # Monitoring events table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS monitoring_events (
        monitoring_event_id TEXT PRIMARY KEY,
        package_id TEXT NOT NULL,
        package_version TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK (event_type IN ('freshness_check','freshness_breach')),
        status TEXT NOT NULL CHECK (status IN ('ok','breach')),
        details_json TEXT,
        created_at_utc TEXT NOT NULL
    );
    """)
    
    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_package ON submissions(package_id, package_version);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_state ON submissions(state);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_validation_runs_submission ON validation_runs(submission_id, created_at_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_submission ON pipeline_jobs(submission_id, created_at_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(entity_type, entity_id, timestamp_utc);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_packages_submission ON evidence_packages(submission_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_monitoring_events_package ON monitoring_events(package_id, package_version, created_at_utc);")
    
    conn.commit()


def seed_test_users():
    """Seed test users for development and testing with authentication."""
    conn = get_connection()
    
    # Import auth service for password hashing
    from src.services.auth import AuthService
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
            created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            roles_str = ','.join(roles)
            
            # For backward compatibility, set role to first role
            primary_role = roles[0] if roles else "submitter"
            
            # Insert user
            conn.execute(
                """INSERT INTO users(user_id, username, password_hash, password_salt, roles, is_active, created_at, display_name, role)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (user_id, username, pwd_hash, salt, roles_str, True, created_at, display_name, primary_role)
            )
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
