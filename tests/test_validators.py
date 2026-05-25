import shutil

from arena.benchmark.case_loader import load_cases
from arena.validators.base import ValidatorContext
from arena.validators.registry import get_validator


def _context(benchmark_dir, tmp_path, case_id, code):
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


def test_fastapi_validator_accepts_dependency_and_role_guards(benchmark_dir, tmp_path):
    dependency = _context(
        benchmark_dir,
        tmp_path,
        "fastapi_auth_bypass_001",
        "from fastapi import Depends\n"
        "def require_admin(): return {}\n"
        "def delete_user(current_user=Depends(require_admin)): return True\n",
    )
    validator = get_validator("fastapi_requires_admin_authorization")
    assert validator.validate(dependency).passed
    decorator = _context(
        benchmark_dir,
        tmp_path,
        "fastapi_auth_bypass_001",
        "from fastapi import Depends\n"
        "def admin_required(): return {}\n"
        "@router.delete('/admin/users', dependencies=[Depends(admin_required)])\n"
        "def delete_user(): return True\n",
    )
    assert validator.validate(decorator).passed
    explicit = _context(
        benchmark_dir,
        tmp_path,
        "fastapi_auth_bypass_001",
        "from fastapi import HTTPException\n"
        "def delete_user(current_user):\n"
        "    if current_user.role != 'admin':\n"
        "        raise HTTPException(status_code=403)\n",
    )
    assert validator.validate(explicit).passed


def test_fastapi_validator_rejects_authentication_only(benchmark_dir, tmp_path):
    context = _context(
        benchmark_dir,
        tmp_path,
        "fastapi_auth_bypass_001",
        "def delete_user(current_user):\n"
        "    if not current_user: raise Exception('login')\n"
        "    return True\n",
    )
    assert not get_validator("fastapi_requires_admin_authorization").validate(context).passed


def test_kafka_validator_requires_guard_not_logging(benchmark_dir, tmp_path):
    logged = _context(
        benchmark_dir,
        tmp_path,
        "kafka_idempotency_bug_001",
        "def handle(self, event):\n"
        "    print(event['event_id'])\n"
        "    self.ledger.credit(event['account_id'], event['amount'])\n",
    )
    assert not get_validator("kafka_idempotency_guard").validate(logged).passed
    guarded = _context(
        benchmark_dir,
        tmp_path,
        "kafka_idempotency_bug_001",
        "def handle(self, event):\n"
        "    if event['event_id'] in self.processed_events: return\n"
        "    self.ledger.credit(event['account_id'], event['amount'])\n"
        "    self.processed_events.add(event['event_id'])\n",
    )
    assert get_validator("kafka_idempotency_guard").validate(guarded).passed


def test_redis_sql_and_rag_validators(benchmark_dir, tmp_path):
    redis_bad = _context(
        benchmark_dir,
        tmp_path,
        "redis_cache_key_collision_001",
        "def cache_key(tenant_id, user_id, query): return f'search:{user_id}'\n",
    )
    redis_good = _context(
        benchmark_dir,
        tmp_path,
        "redis_cache_key_collision_001",
        "def cache_key(tenant_id, user_id, query):\n"
        "    return f'search:{tenant_id}:{user_id}:{query}'\n",
    )
    redis = get_validator("redis_cache_key_has_tenant_scope")
    assert not redis.validate(redis_bad).passed
    assert redis.validate(redis_good).passed
    sql_bad = _context(
        benchmark_dir,
        tmp_path,
        "sql_permission_leak_001",
        "SELECT * FROM documents WHERE id=:id;\n",
    )
    sql_good = _context(
        benchmark_dir,
        tmp_path,
        "sql_permission_leak_001",
        "SELECT * FROM documents WHERE id=:id AND organization_id=:organization_id;\n",
    )
    sql = get_validator("sql_has_tenant_or_owner_filter")
    assert not sql.validate(sql_bad).passed
    assert sql.validate(sql_good).passed
    rag_bad = _context(
        benchmark_dir,
        tmp_path,
        "rag_fake_citation_001",
        "def build_answer(generator, retrieved_chunks): return generator(retrieved_chunks)\n",
    )
    rag_good = _context(
        benchmark_dir,
        tmp_path,
        "rag_fake_citation_001",
        "def build_answer(generator, retrieved_chunks):\n"
        "    answer = generator(retrieved_chunks)\n"
        "    valid_ids = {chunk['id'] for chunk in retrieved_chunks}\n"
        "    if any(cid not in valid_ids for cid in answer['citation_ids']): raise ValueError()\n"
        "    return answer\n",
    )
    rag = get_validator("rag_citation_ids_validated")
    assert not rag.validate(rag_bad).passed
    assert rag.validate(rag_good).passed
