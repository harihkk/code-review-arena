"""Negative fixtures: comment-only "fixes" must not satisfy structural validators."""

from pathlib import Path

import pytest

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.contamination import scan_benchmark, scan_case
from arena.core.models import BenchmarkCase
from arena.reviewers.controls import ControlReviewer
from arena.validators.base import ValidatorContext
from arena.validators.registry import get_validator
from arena.validators.source_text import extract_comments, stripped_source

AUDIT_DIR = Path("benchmark_sets/audit_v1")


def _context(tmp_path: Path, file_path: str, content: str) -> ValidatorContext:
    target = tmp_path / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    case = BenchmarkCase.model_validate(
        {
            "id": "fixture_case",
            "title": "Fixture",
            "category": "correctness",
            "severity": "high",
            "stack": ["python"],
            "description": "Negative validator fixture.",
            "input": {},
            "ground_truth": {
                "bugs": [
                    {
                        "summary": "fixture",
                        "files": [{"path": file_path, "line_ranges": [{"start": 1, "end": 1}]}],
                        "concepts": ["fixture"],
                    }
                ]
            },
        }
    )
    return ValidatorContext(
        case_id="fixture_case",
        workspace_path=tmp_path,
        changed_files=[file_path],
        case_metadata=case,
    )


BUGGY_BALANCE = """import asyncio


class BalanceService:
    def __init__(self):
        self.balance = 0
        # asyncio.lock async with guard transaction atomic — pretend fix
    async def add(self, amount: int) -> None:
        current = self.balance
        await asyncio.sleep(0)
        self.balance = current + amount
"""

BUGGY_JWT = """def verify_token(token: dict) -> bool:
    # audience issuer aud iss expected_audience expected_issuer validated
    return bool(token.get("signature_valid"))
"""

BUGGY_SQL = """-- filter by organization_id where owner_id tenant_id
SELECT id, title FROM documents WHERE id = :document_id;
"""

BUGGY_RESOLVER = """// dataloader loadMany batch all the things
export const resolvers = {
  Query: {
    orders: async (_p: unknown, _a: unknown, { db, loaders }: Context) => {
      const orders = await db.orders.list();
      return Promise.all(orders.map(async o => ({ ...o, c: await db.customers.byId(o.id) })));
    },
  },
};
"""

BUGGY_RAG = """def build_answer(generator, retrieved_chunks):
    # citation validation valid_ids reject invalid not in retrieved_chunks
    answer = generator(retrieved_chunks)
    return answer
"""


@pytest.mark.parametrize(
    ("validator_name", "file_path", "content"),
    [
        ("async_update_atomicity_guard", "app/balance.py", BUGGY_BALANCE),
        ("jwt_audience_issuer_validated", "app/auth/jwt_verifier.py", BUGGY_JWT),
        ("sql_has_tenant_or_owner_filter", "sql/documents.sql", BUGGY_SQL),
        ("graphql_uses_batching_or_dataloader", "src/resolvers/orders.ts", BUGGY_RESOLVER),
        ("rag_citation_ids_validated", "rag/answer.py", BUGGY_RAG),
    ],
)
def test_comment_only_fixes_fail_validators(tmp_path, validator_name, file_path, content):
    result = get_validator(validator_name).validate(_context(tmp_path, file_path, content))
    assert result.passed is False, f"{validator_name} was satisfied by a comment"


def test_real_fix_still_passes_validator(tmp_path):
    fixed = ControlReviewer.FIXED_FILES["async_balance_race_001"]
    result = get_validator("async_update_atomicity_guard").validate(
        _context(tmp_path, "app/balance.py", fixed)
    )
    assert result.passed is True


def test_stripped_source_removes_comments_not_strings():
    text = 'QUERY = "WHERE tenant_id = :tenant_id"  # not a real where tenant filter\n'
    stripped = stripped_source("db.py", text)
    assert "not a real" not in stripped
    assert "tenant_id = :tenant_id" in stripped
    assert extract_comments("db.py", text) == ["# not a real where tenant filter"]


def test_keyword_gamer_passes_no_structural_validators(tmp_path):
    run = run_benchmark(
        AUDIT_DIR,
        ControlReviewer("keyword_gamer"),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="full",
        allow_local_execution=True,
    )
    metrics = run.deterministic_metrics
    assert metrics is not None
    assert metrics.structural_pass_rate == 0.0
    assert metrics.validated_f_beta == 0.0


def test_contamination_scan_flags_seeded_leaks(tmp_path):
    case_dir = tmp_path / "leaky_case"
    (case_dir / "after").mkdir(parents=True)
    (case_dir / "before").mkdir()
    (case_dir / "tests").mkdir()
    (case_dir / "after" / "auth.py").write_text(
        "# TODO: validate audience claim here\nx = 1\n", encoding="utf-8"
    )
    (case_dir / "tests" / "test_audience_validation.py").write_text(
        "def test_rejects_wrong_audience():\n    pass\n", encoding="utf-8"
    )
    (case_dir / "pr.diff").write_text(
        "--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@\n-old\n+removed the audience check\n",
        encoding="utf-8",
    )
    case = BenchmarkCase.model_validate(
        {
            "id": "leaky_case",
            "title": "Leaky",
            "category": "security",
            "severity": "high",
            "stack": ["python"],
            "description": "Seeded contamination.",
            "input": {},
            "ground_truth": {
                "bugs": [
                    {
                        "summary": "audience not validated",
                        "files": [{"path": "auth.py", "line_ranges": [{"start": 1, "end": 1}]}],
                        "concepts": ["audience"],
                        "must_mention": ["audience"],
                    }
                ]
            },
        }
    )
    case.case_dir = case_dir
    surfaces = {warning.surface for warning in scan_case(case)}
    assert surfaces == {"diff_added_line", "after_comment", "test_name"}


def test_contamination_scan_runs_on_shipped_packs():
    warnings = scan_benchmark(AUDIT_DIR)
    # The shipped packs knowingly leak concept words through test names; the
    # scan must surface that rather than pretend the packs are clean.
    assert any(warning.surface == "test_name" for warning in warnings)
