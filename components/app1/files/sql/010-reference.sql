CREATE TABLE IF NOT EXISTS demo_seed (name text PRIMARY KEY, value text NOT NULL);
INSERT INTO demo_seed (name, value) VALUES ('reference', 'release-v1')
ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value;
