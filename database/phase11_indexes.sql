-- Apply once to an existing freelancer_pms database.
-- New database installs get this index from schema.sql.
USE freelancer_pms;

CREATE INDEX ix_payment_milestone_status
  ON Payment (milestone_id, status);
