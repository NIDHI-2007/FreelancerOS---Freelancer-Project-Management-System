-- One-time update for databases created before the final demo reset flow.
USE freelancer_pms;
DROP TABLE IF EXISTS Password_Reset_Token;

-- Mirror the completed-payment invariant in the current schema.
ALTER TABLE Payment
  ADD CONSTRAINT chk_completed_payment_reference CHECK
    (status <> 'completed' OR (transaction_reference IS NOT NULL AND CHAR_LENGTH(TRIM(transaction_reference)) > 0));
