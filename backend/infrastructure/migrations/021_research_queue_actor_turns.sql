-- Durable round-robin claim order for the operational job queue only.
-- This table is not command, receipt, financial, or user-visible authority.
CREATE TABLE btl.research_queue_actor_turns (
    actor_id uuid PRIMARY KEY REFERENCES btl.users(id),
    last_claimed_at timestamptz NOT NULL
);
