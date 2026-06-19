"""Deterministic lexical concept matching.

This baseline is intentionally lexical: it matches each curated phrase as a
contiguous, word-bounded token sequence in the finding text. It is not semantic
similarity; paraphrases that avoid every curated token are under-credited.
Semantic backends (embedding or judge based) can be layered on top, but the
deterministic baseline must stay reproducible without models.

Matching is deliberately not a bare substring or an unordered token bag: "lock"
must not match "blocked", and "access control" must not be earned by an
unordered "controls who can access". Otherwise a reviewer could top the concept
dimension by dumping the vocabulary in any order.
"""

from __future__ import annotations

import re

from arena.core.models import Finding, GroundTruthBug

# Relative shares of the concept dimension (category : must_mention : concepts).
_CATEGORY_SHARE = 10.0
_MUST_MENTION_SHARE = 15.0
_CONCEPTS_SHARE = 10.0
_TOTAL_SHARE = _CATEGORY_SHARE + _MUST_MENTION_SHARE + _CONCEPTS_SHARE


def mentions(text: str, phrase: str) -> bool:
    tokens = phrase.casefold().split()
    if not tokens:
        return False
    # The phrase must appear as a contiguous, word-bounded token sequence.
    pattern = r"\b" + r"\s+".join(re.escape(token) for token in tokens) + r"\b"
    return re.search(pattern, text.casefold()) is not None


def finding_text(finding: Finding) -> str:
    return " ".join([finding.title, finding.summary, finding.evidence, finding.suggested_fix or ""])


def concept_ratio(finding: Finding, bug: GroundTruthBug, case_category: str) -> float:
    """Return the 0..1 fraction of the concept weight earned by this finding."""
    text = finding_text(finding)
    category = _CATEGORY_SHARE if finding.category == case_category else 0.0
    must_ratio = (
        sum(mentions(text, phrase) for phrase in bug.must_mention) / len(bug.must_mention)
        if bug.must_mention
        else 1
    )
    concepts = (
        sum(mentions(text, phrase) for phrase in bug.concepts) / len(bug.concepts)
        if bug.concepts
        else 1
    )
    earned = category + (_MUST_MENTION_SHARE * must_ratio) + (_CONCEPTS_SHARE * concepts)
    return round(earned / _TOTAL_SHARE, 6)
