-- Compatibility marker. The Python migration runner conditionally adds missing
-- columns because SQLite/libSQL do not support ADD COLUMN IF NOT EXISTS.
SELECT 1;
