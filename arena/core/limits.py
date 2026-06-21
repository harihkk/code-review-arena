"""Centralized, documented size and count limits for external input.

These are OPERATIONAL SAFETY bounds (denial-of-service and memory protection),
not claims about semantic correctness. They are chosen with generous headroom
over the maxima observed across the shipped packs, control-reviewer outputs, and
run fixtures, but are deliberately finite so an adversarial pack, reviewer, or API
client cannot drive the harness into pathological memory or compute. External
input that exceeds a bound is REJECTED with a located validation error, never
silently truncated (the one exception is the reviewer source context, whose
truncation is an explicit, recorded part of that contract).

Observed maxima at the time of writing (benchmark_sets/v1, audit_v1, audit_v2):
manifest 451 B, case.yaml 1291 B, pr.diff 1071 B, reference.patch 1021 B,
10 cases/manifest, 1 bug/case, 1 file/bug, 1 line-range/file, 4 concepts,
5 fix keywords, 4 stack entries, title 75, description 201, category 19,
case id 45, concept 26, test_command string 15. Limits below sit well above these.
"""

from __future__ import annotations

# --- Pre-parse raw document byte caps (checked before YAML/JSON parsing) ---
MANIFEST_BYTES = 256 * 1024
CASE_YAML_BYTES = 512 * 1024
DIFF_BYTES = 4 * 1024 * 1024
PATCH_BYTES = 4 * 1024 * 1024

# An individual pack source / test / ground-truth file (read to hash, count
# lines, scan for contamination, or build reviewer context). Generous, but finite.
PACK_FILE_BYTES = 8 * 1024 * 1024
# pack.sha256 is a single hex digest line.
CHECKSUM_FILE_BYTES = 256

# --- Pack structure counts ---
CASES_PER_MANIFEST = 1024
BUGS_PER_CASE = 50  # also the finding-to-bug matching cap (MAX_BUGS_PER_CASE)
FILES_PER_BUG = 128
LINE_RANGES_PER_FILE = 256
ACCEPTABLE_FINDINGS_PER_CASE = 128
STACK_ENTRIES = 32
CONCEPTS_PER_BUG = 128
MUST_MENTION_PER_BUG = 128
FIX_KEYWORDS_PER_BUG = 128
PROTECTED_PATHS_PER_CASE = 512
STRUCTURAL_VALIDATORS_PER_CASE = 64
ARGV_COMMANDS = 32
ARGV_TOKENS = 256

# --- Pack string-length caps ---
TITLE_LEN = 1024
DESCRIPTION_LEN = 16 * 1024
CATEGORY_LEN = 128
IDENTIFIER_LEN = 128  # case ids; matches the case-id length bound in security.paths
SUMMARY_LEN = 4 * 1024
CONCEPT_LEN = 256
PHRASE_LEN = 256  # must_mention / fix keywords / structural validator names
TOKEN_LEN = 4096  # one argv token
COMMAND_STRING_LEN = 16 * 1024  # a test_command / static_analysis_command string
DOCKER_IMAGE_REF_LEN = 512
LINE_NUMBER_MAX = 10_000_000  # bound line-number magnitude (start/end)

# --- Reviewer-visible input (mirrors ContextLimits; see arena/benchmark/case_loader) ---
RELEVANT_FILE_COUNT = 40
RELEVANT_FILE_BYTES = 64 * 1024
RELEVANT_FILES_TOTAL_BYTES = 256 * 1024
OMITTED_FILE_COUNT = 4096
TEST_OUTPUT_BYTES = 512 * 1024
STATIC_ANALYSIS_OUTPUT_BYTES = 512 * 1024

# --- Reviewer output ---
RAW_RESPONSE_BYTES = 2 * 1024 * 1024
FINDINGS_PER_RESPONSE = 200  # MAX_FINDINGS_PER_RESPONSE
FINDING_TITLE_LEN = 1024
FINDING_SUMMARY_LEN = 8 * 1024
EVIDENCE_LEN = 16 * 1024
SUGGESTED_FIX_LEN = 64 * 1024
PATCH_LEN = 4 * 1024 * 1024  # per-finding suggested_patch and case-level proposed_patch
REPLACEMENT_CODE_LEN = 256 * 1024
REVIEW_SUMMARY_LEN = 16 * 1024
TOOL_USAGE_ENTRIES = 256
TOOL_USAGE_ENTRY_LEN = 1024

# --- API request ---
API_REQUEST_BODY_BYTES = 256 * 1024
BENCHMARK_SET_NAME_LEN = 256
REVIEWER_ID_LEN = 256
COMMAND_LEN = 16 * 1024
MODEL_ID_LEN = 256
