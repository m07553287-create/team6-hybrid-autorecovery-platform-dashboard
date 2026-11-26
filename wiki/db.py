"""SQLite 연결과 스키마 (스펙 6.2)."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams(
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  pw_hash TEXT NOT NULL, pw_salt TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id),
  member TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(
  key TEXT PRIMARY KEY, count INTEGER NOT NULL, window_start INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), kind TEXT NOT NULL,
  parent_id INTEGER NULL REFERENCES docs(id), sort INTEGER NOT NULL DEFAULT 0,
  current_rev INTEGER NOT NULL, current_body TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS revisions(
  id INTEGER PRIMARY KEY, doc_id INTEGER NOT NULL REFERENCES docs(id), rev INTEGER NOT NULL,
  body TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, author TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, UNIQUE(doc_id, rev));
CREATE TABLE IF NOT EXISTS scripts(
  id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id), path TEXT NOT NULL,
  host TEXT NOT NULL, status TEXT NOT NULL, keys TEXT NOT NULL, text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS docs_team ON docs(team_id, deleted);
CREATE INDEX IF NOT EXISTS rev_doc ON revisions(doc_id, rev);
CREATE INDEX IF NOT EXISTS rev_time ON revisions(created_at);
CREATE INDEX IF NOT EXISTS sessions_team ON sessions(team_id);
"""


def connect(path):
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # 자동커밋, 트랜잭션은 BEGIN 으로
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
