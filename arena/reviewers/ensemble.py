"""Ensemble reviewer that merges provider findings."""

from __future__ import annotations

import json

from arena.core.models import CaseContext, ReviewerResponse, ReviewResult
from arena.reviewers.base import BaseReviewer


class EnsembleReviewer(BaseReviewer):
    name = "ensemble"

    def __init__(self, reviewers: list[BaseReviewer]) -> None:
        if not reviewers:
            raise ValueError("An ensemble needs at least one reviewer.")
        self.reviewers = reviewers
        self.model = ",".join(reviewer.identifier for reviewer in reviewers)

    def review(self, context: CaseContext) -> ReviewerResponse:
        responses = [reviewer.review(context) for reviewer in self.reviewers]
        findings = []
        summaries = []
        for response in responses:
            if response.parsed_response:
                findings.extend(response.parsed_response.findings)
                summaries.append(response.parsed_response.review_summary)
        result = ReviewResult(
            findings=findings,
            overall_risk=max(
                (r.parsed_response.overall_risk for r in responses if r.parsed_response),
                default="none",
                key=lambda risk: ["none", "low", "medium", "high", "critical"].index(risk),
            ),
            review_summary=" | ".join(summaries),
        )
        return ReviewerResponse(
            raw_response=json.dumps(result.model_dump()),
            parsed_response=result,
            invalid_output=False,
            parse_attempts=1,
            latency_ms=sum(response.latency_ms for response in responses),
            input_tokens=sum(response.input_tokens for response in responses),
            output_tokens=sum(response.output_tokens for response in responses),
            estimated_cost=sum(response.estimated_cost for response in responses),
        )
