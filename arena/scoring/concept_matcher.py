"""Deterministic lexical concept matching.

This baseline is intentionally lexical: case-folded substring and whole-token
matching against the curated `must_mention`/`concepts` phrases of a bug. It is
not semantic similarity; paraphrases that avoid every curated token are
under-credited. Semantic backends (embedding or judge based) can be layered on
top, but the deterministic baseline must stay reproducible without models.
"""

from __future__ import annotations

from arena.core.models import Finding, GroundTruthBug

# Relative shares of the concept dimension (category : must_mention : concepts).
_CATEGORY_SHARE = 10.0
_MUST_MENTION_SHARE = 15.0
_CONCEPTS_SHARE = 10.0
_TOTAL_SHARE = _CATEGORY_SHARE + _MUST_MENTION_SHARE + _CONCEPTS_SHARE


def mentions(text: str, phrase: str) -> bool:
    normalized = text.casefold()
    phrase = phrase.casefold()
    return phrase in normalized or all(token in normalized for token in phrase.split())


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
