-- Harmless public demo marker. Sensitive dev data belongs outside files/.
INSERT INTO demo_seed (name, value) VALUES ('dev-sample', 'dev-only')
ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value;
