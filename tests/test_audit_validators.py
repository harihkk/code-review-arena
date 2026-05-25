import shutil
from pathlib import Path

import pytest

from arena.benchmark.case_loader import load_cases
from arena.validators.base import ValidatorContext
from arena.validators.registry import get_validator


@pytest.fixture
def audit_benchmark_dir() -> Path:
    return Path("benchmark_sets/audit_v1")


def _context(benchmark_dir: Path, tmp_path, case_id: str, code: str):
    case = next(item for item in load_cases(benchmark_dir) if item.id == case_id)
    workspace = tmp_path / f"{case_id}-{len(list(tmp_path.iterdir()))}"
    shutil.copytree(case.case_dir / case.input.after_dir, workspace)
    target = case.ground_truth.primary_bug.files[0].path
    (workspace / target).write_text(code, encoding="utf-8")
    return ValidatorContext(
        case_id=case_id,
        workspace_path=workspace,
        changed_files=[target],
        case_metadata=case,
    )


def test_fastapi_tenant_admin_validator_positive_and_negative(audit_benchmark_dir, tmp_path):
    validator = get_validator("fastapi_tenant_admin_authorization")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "security_fastapi_multitenant_admin_bypass_001",
        "from fastapi import Depends\n"
        "def reset_tenant(tenant_id: str, current_user=Depends(require_tenant_admin)):\n"
        "    return True\n",
    )
    assert validator.validate(good).passed
    bad = _context(
        audit_benchmark_dir,
        tmp_path,
        "security_fastapi_multitenant_admin_bypass_001",
        "from fastapi import Depends\n"
        "def reset_tenant(tenant_id: str, current_user=Depends(get_current_user)):\n"
        "    return True\n",
    )
    assert not validator.validate(bad).passed


def test_kafka_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("kafka_idempotency_guard")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "distributed_kafka_duplicate_event_001",
        "def handle(self, event):\n"
        "    if event['event_id'] in self.processed_event_ids: return\n"
        "    self.ledger.credit(event['account_id'], event['amount'])\n"
        "    self.processed_event_ids.add(event['event_id'])\n",
    )
    assert validator.validate(good).passed


def test_rag_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("rag_citation_ids_validated")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "rag_fabricated_citation_001",
        "def build_answer(generator, retrieved_chunks):\n"
        "    answer = generator(retrieved_chunks)\n"
        "    valid_ids = {chunk['id'] for chunk in retrieved_chunks}\n"
        "    if any(citation not in valid_ids for citation in answer['citation_ids']):\n"
        "        raise ValueError('unsupported')\n"
        "    return answer\n",
    )
    assert validator.validate(good).passed


def test_async_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("async_update_atomicity_guard")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "async_balance_race_001",
        "import asyncio\n"
        "class BalanceService:\n"
        "    def __init__(self):\n"
        "        self.balance = 0\n"
        "        self.lock = asyncio.Lock()\n"
        "    async def add(self, amount):\n"
        "        async with self.lock:\n"
        "            current = self.balance\n"
        "            self.balance = current + amount\n",
    )
    assert validator.validate(good).passed
    bad = _context(
        audit_benchmark_dir,
        tmp_path,
        "async_balance_race_001",
        "class BalanceService:\n"
        "    async def add(self, amount):\n"
        "        current = self.balance\n"
        "        self.balance = current + amount\n",
    )
    assert not validator.validate(bad).passed


def test_tenant_scoped_idempotency_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("tenant_scoped_idempotency_key")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "idempotency_key_tenant_scope_001",
        "class IdempotencyStore:\n"
        "    def lookup(self, tenant_id, key):\n"
        "        return self._records.get((tenant_id, key))\n"
        "    def store(self, tenant_id, key, response):\n"
        "        self._records[(tenant_id, key)] = response\n",
    )
    assert validator.validate(good).passed
    bad = _context(
        audit_benchmark_dir,
        tmp_path,
        "idempotency_key_tenant_scope_001",
        "class IdempotencyStore:\n"
        "    def lookup(self, tenant_id, key):\n"
        "        return self._records.get(key)\n",
    )
    assert not validator.validate(bad).passed


def test_sql_tenant_filter_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("sql_has_tenant_or_owner_filter")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "security_sql_join_ownership_leak_001",
        'DOCUMENT_LOOKUP_SQL = """\\nWHERE d.id = :document_id\\n'
        '  AND d.organization_id = :organization_id\\n"""\n',
    )
    assert validator.validate(good).passed


def test_jwt_audience_issuer_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("jwt_audience_issuer_validated")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "security_jwt_audience_validation_001",
        "def verify_token(token):\n"
        "    if token.get('aud') != EXPECTED_AUDIENCE: return False\n"
        "    if token.get('iss') != EXPECTED_ISSUER: return False\n"
        "    return True\n",
    )
    assert validator.validate(good).passed


def test_event_version_guard_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("event_version_monotonic_guard")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "distributed_out_of_order_event_001",
        "def apply(self, event):\n"
        "    if event.version <= self.state.version: return self.state\n"
        "    self.state.status = event.status\n",
    )
    assert validator.validate(good).passed


def test_pagination_tiebreaker_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("pagination_uses_stable_tiebreaker")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "api_pagination_cursor_skip_001",
        "def fetch_page(records, *, cursor, limit):\n"
        "    ordered = sorted(records, key=lambda item: (item.created_at, item.id))\n"
        "    next_cursor = (last.created_at, last.id)\n",
    )
    assert validator.validate(good).passed


def test_rag_untrusted_context_validator_case_specific(audit_benchmark_dir, tmp_path):
    validator = get_validator("rag_retrieved_context_is_untrusted")
    good = _context(
        audit_benchmark_dir,
        tmp_path,
        "rag_prompt_injection_policy_override_001",
        "def build_prompt(*, system_instructions, retrieved):\n"
        '    return f"SYSTEM_INSTRUCTIONS:\\n{system_instructions}\\n\\n"\n'
        '        f"RETRIEVED_CONTEXT_DATA:\\n[UNTRUSTED_RETRIEVED_CONTEXT]"\n',
    )
    assert validator.validate(good).passed
