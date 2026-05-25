PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  reviewer TEXT NOT NULL,
  model TEXT,
  benchmark_set TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  total_score REAL NOT NULL,
  total_cost REAL NOT NULL,
  total_latency_ms INTEGER NOT NULL,
  beta REAL,
  deterministic_precision REAL,
  deterministic_recall REAL,
  deterministic_f1 REAL,
  deterministic_f_beta REAL,
  detection_precision REAL,
  detection_recall REAL,
  detection_f1 REAL,
  detection_f_beta REAL,
  validated_precision REAL,
  validated_recall REAL,
  validated_f1 REAL,
  validated_f_beta REAL,
  deterministic_pass_rate REAL,
  patch_apply_rate REAL,
  test_pass_rate REAL,
  structural_pass_rate REAL,
  false_positives_per_case REAL,
  cost_per_true_positive REAL,
  cost_per_validated_fix REAL,
  latency_per_case_ms REAL,
  run_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_results (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL,
  score REAL NOT NULL,
  bug_found BOOLEAN NOT NULL,
  correct_file BOOLEAN NOT NULL,
  correct_line BOOLEAN NOT NULL,
  false_positive_count INTEGER NOT NULL,
  deterministic_pass BOOLEAN,
  patch_provided BOOLEAN,
  patch_applied BOOLEAN,
  tests_ran BOOLEAN,
  tests_passed BOOLEAN,
  structural_validation_ran BOOLEAN,
  structural_validation_passed BOOLEAN,
  failure_reasons_json TEXT,
  patch_error TEXT,
  raw_response TEXT NOT NULL,
  parsed_response TEXT
);

CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  case_result_id TEXT NOT NULL REFERENCES case_results(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  severity TEXT NOT NULL,
  file TEXT NOT NULL,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  summary TEXT NOT NULL,
  suggested_fix TEXT,
  confidence REAL NOT NULL,
  is_true_positive BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS validator_results (
  id TEXT PRIMARY KEY,
  case_result_id TEXT NOT NULL REFERENCES case_results(id) ON DELETE CASCADE,
  validator_name TEXT NOT NULL,
  passed BOOLEAN NOT NULL,
  confidence REAL NOT NULL,
  message TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  error TEXT
);
