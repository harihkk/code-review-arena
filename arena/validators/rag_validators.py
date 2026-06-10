"""Static evidence that RAG citations are checked against retrieved sources."""

from __future__ import annotations

import re

from arena.validators.base import (
    BaseValidator,
    ValidatorContext,
    ValidatorResult,
    read_expected_source,
)


class RAGCitationIdsValidated(BaseValidator):
    name = "rag_citation_ids_validated"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        source = any(
            term in lower
            for term in ["retrieved_chunks", "source_ids", "valid_ids", "allowed_citations"]
        )
        citation = "citation" in lower
        decision = any(
            marker in lower
            for marker in [
                "not in",
                "raise ",
                "reject",
                "invalid",
                "allowed_citations",
                "valid_ids",
            ]
        )
        passed = source and citation and decision
        evidence = []
        if source:
            evidence.append("Validation references IDs derived from retrieved source context.")
        if citation and decision:
            evidence.append("Returned citations are rejected or filtered when unsupported.")
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.93 if passed else 0.9,
            message=(
                "Generated citation IDs are constrained by retrieved sources."
                if passed
                else "Generated citations are still returned without source-ID validation."
            ),
            evidence=evidence,
        )


class RAGRetrievedContextIsUntrusted(BaseValidator):
    name = "rag_retrieved_context_is_untrusted"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        evidence: list[str] = []
        labels = [
            "untrusted",
            "retrieved context",
            "retrieved_context",
            "user context",
            "external context",
            "context data",
        ]
        separation = any(
            marker in lower
            for marker in [
                "untrusted_retrieved",
                "retrieved_context_section",
                "context_block",
                "wrap_retrieved",
                "format_retrieved",
                "--- retrieved",
                "role: user",
                "data only",
            ]
        )
        labelled = any(label.replace(" ", "_") in lower or label in lower for label in labels)
        system_preserved = "system_instructions" in lower or "system_prompt" in lower
        direct_concat = bool(
            re.search(
                r"system[_\s]*(?:instructions|prompt).{0,120}\+\s*retrieved",
                lower,
                flags=re.DOTALL,
            )
            or re.search(
                r"return\s+system[_\s]*(?:instructions|prompt).{0,80}\+\s*",
                lower,
                flags=re.DOTALL,
            )
        )
        passed = (separation or labelled) and system_preserved and not direct_concat
        if separation or labelled:
            evidence.append("Retrieved content is labelled or wrapped as untrusted context.")
        if system_preserved:
            evidence.append("System instructions remain separate from retrieved content.")
        if direct_concat:
            evidence.append("Retrieved text is concatenated directly into system instructions.")
            passed = False
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.92 if passed else 0.9,
            message=(
                "Retrieved context is isolated from trusted system instructions."
                if passed
                else "Retrieved content can override trusted system instructions."
            ),
            evidence=evidence,
        )
