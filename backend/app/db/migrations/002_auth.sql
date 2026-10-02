
CREATE TABLE oauth_flows (
    state_hash TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    nonce_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX idx_oauth_flows_expiry
ON oauth_flows(expires_at);
