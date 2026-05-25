"""Deterministic lexical concept matching baseline."""

from __future__ import annotations

from arena.core.models import BenchmarkCase, Finding


def _mentions(text: str, phrase: str) -> bool:
    normalized = text.casefold()
    phrase = phrase.casefold()
    return phrase in normalized or all(token in normalized for token in phrase.split())


def concept_score(finding: Finding, case: BenchmarkCase) -> float:
    bug = case.ground_truth.primary_bug
    text = " ".join([finding.title, finding.summary, finding.evidence, finding.suggested_fix or ""])
    category = 10 if finding.category == case.category else 0
    must_ratio = (
        sum(_mentions(text, phrase) for phrase in bug.must_mention) / len(bug.must_mention)
        if bug.must_mention
        else 1
    )
    concept_ratio = (
        sum(_mentions(text, phrase) for phrase in bug.concepts) / len(bug.concepts)
        if bug.concepts
        else 1
    )
    return round(category + (15 * must_ratio) + (10 * concept_ratio), 2)
