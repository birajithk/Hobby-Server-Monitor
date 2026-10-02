
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT,
    google_sub TEXT UNIQUE,

    role TEXT NOT NULL
        CHECK (role IN ('admin', 'container_user')),

    status TEXT NOT NULL DEFAULT 'invited'
        CHECK (status IN ('invited', 'active', 'revoked')),

    quota_ram_bytes INTEGER NOT NULL DEFAULT 0
        CHECK (quota_ram_bytes >= 0),

    quota_cpu_cores INTEGER NOT NULL DEFAULT 0
        CHECK (quota_cpu_cores >= 0),

    quota_disk_bytes INTEGER NOT NULL DEFAULT 0
        CHECK (quota_disk_bytes >= 0),

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS containers (
    id TEXT PRIMARY KEY,

    lxd_project TEXT NOT NULL DEFAULT 'default',
    lxd_name TEXT NOT NULL,

    owner_id TEXT NOT NULL,

    image TEXT,
    description TEXT,

    ram_limit_bytes INTEGER NOT NULL
        CHECK (ram_limit_bytes > 0),

    cpu_limit_cores INTEGER NOT NULL
        CHECK (cpu_limit_cores > 0),

    cpu_allowance_percent INTEGER
        CHECK (
            cpu_allowance_percent IS NULL
            OR cpu_allowance_percent BETWEEN 1 AND 100
        ),

    disk_limit_bytes INTEGER NOT NULL
        CHECK (disk_limit_bytes > 0),

    storage_pool TEXT NOT NULL,
    network_name TEXT,

    ephemeral INTEGER NOT NULL DEFAULT 0
        CHECK (ephemeral IN (0, 1)),

    autostart INTEGER NOT NULL DEFAULT 0
        CHECK (autostart IN (0, 1)),

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE (lxd_project, lxd_name),

    FOREIGN KEY (owner_id)
        REFERENCES users(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_containers_owner
ON containers(owner_id);

CREATE TABLE IF NOT EXISTS container_access (
    container_id TEXT NOT NULL,
    user_id TEXT NOT NULL,

    created_at TEXT NOT NULL,

    PRIMARY KEY (container_id, user_id),

    FOREIGN KEY (container_id)
        REFERENCES containers(id)
        ON DELETE CASCADE,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_access_user
ON container_access(user_id);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,

    user_id TEXT NOT NULL,
    csrf_token_hash TEXT NOT NULL,

    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user
ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_expiry
ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,

    actor_user_id TEXT,
    actor_email_snapshot TEXT,

    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,

    details TEXT,

    created_at TEXT NOT NULL,

    FOREIGN KEY (actor_user_id)
        REFERENCES users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created
ON audit_logs(created_at);