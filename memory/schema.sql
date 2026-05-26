-- ── Run this once in your Supabase SQL editor ──────────────────────
-- Two tables only. No chat_history table — raw messages live in
-- session_state; only distilled knowledge is persisted.

-- Per-paper memory: corrections, self-revisions, established facts,
-- and compressed conversation summaries (sliding window).
CREATE TABLE IF NOT EXISTS memory_paper (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id    TEXT NOT NULL,
    type        TEXT NOT NULL,   -- 'correction' | 'self_revision' | 'established_fact' | 'conversation_summary'
    content     TEXT NOT NULL,
    turn_range  TEXT,            -- e.g. "1-5" — which turns this summary covers
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_paper_paper_id ON memory_paper(paper_id);
CREATE INDEX IF NOT EXISTS idx_memory_paper_type     ON memory_paper(type);

-- Global user memory: expertise signals and style preferences
-- that carry across all papers.
CREATE TABLE IF NOT EXISTS memory_user (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type       TEXT NOT NULL,   -- 'expertise_signal' | 'style_preference'
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memory_user_type ON memory_user(type);
