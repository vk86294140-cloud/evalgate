"""Source grounding: is the answer actually supported by what was retrieved?

Two failures matter and they are different. A *fabricated citation* is a quote
the model attributes to the context when the context never said it. An
*unsupported claim* is a sentence in the answer that no citation backs. The
first is the dangerous one, so it fails the check outright; the second is
scored, because a little connective prose is normal.
"""

from __future__ import annotations

import re
from typing import Any

from ..dataset import Case
from .base import CheckResult, get_field, register

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'%$.-]*")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

_STOPWORDS = frozenset(
    """a an and are as at be but by for from had has have if in into is it its of on or
    that the their then there these they this to was were will with you your our we""".split()
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if w.lower() not in _STOPWORDS and len(w) > 1}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text.strip()) if s.strip()]


@register("grounding")
class GroundingCheck:
    name = "grounding"

    def __init__(
        self,
        root: Any = None,
        answer_field: str = "answer",
        citations_field: str = "citations",
        context_field: str = "context",
        min_support: float = 0.8,
        min_overlap: float = 0.4,
        allow_abstain: bool = True,
        **_: Any,
    ) -> None:
        self.answer_field = answer_field
        self.citations_field = citations_field
        self.context_field = context_field
        self.min_support = float(min_support)
        self.min_overlap = float(min_overlap)
        self.allow_abstain = allow_abstain

    def _context(self, case: Case, output: dict[str, Any]) -> str:
        value = get_field(output, self.context_field)
        if value is None:
            value = get_field(case.input, self.context_field)
        if isinstance(value, list):
            return "\n".join(str(v) for v in value)
        return str(value or "")

    def _citations(self, output: dict[str, Any]) -> list[str]:
        raw = get_field(output, self.citations_field) or []
        if isinstance(raw, str):
            raw = [raw]
        out: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                quote = item.get("quote") or item.get("text") or item.get("span")
                if quote:
                    out.append(str(quote))
            elif item:
                out.append(str(item))
        return out

    def run(self, case: Case, output: dict[str, Any]) -> CheckResult:
        answer = get_field(output, self.answer_field)
        if not isinstance(answer, str) or not answer.strip():
            return CheckResult(self.name, False, 0.0, f"{self.answer_field} is empty")

        if self.allow_abstain and bool(output.get("abstained")):
            return CheckResult(self.name, True, 1.0, "system abstained, nothing to ground")

        context = self._context(case, output)
        if not context:
            return CheckResult(self.name, False, 0.0, "no context available to ground against")

        haystack = normalize(context)
        citations = self._citations(output)
        fabricated = [c for c in citations if normalize(c) and normalize(c) not in haystack]

        claims = sentences(answer)
        cite_tokens = [tokens(c) for c in citations if normalize(c) in haystack]
        unsupported: list[str] = []
        for claim in claims:
            claim_tokens = tokens(claim)
            if not claim_tokens:
                continue
            best = max(
                (len(claim_tokens & ct) / len(claim_tokens) for ct in cite_tokens),
                default=0.0,
            )
            if best < self.min_overlap:
                unsupported.append(claim)

        scored = [c for c in claims if tokens(c)]
        support = 1.0 if not scored else (len(scored) - len(unsupported)) / len(scored)

        if fabricated:
            detail = f"{len(fabricated)} citation(s) do not appear in the context: {fabricated[0][:80]!r}"
            passed = False
        elif not citations:
            detail = "answer has no citations"
            passed = False
        else:
            passed = support >= self.min_support
            detail = (
                f"{len(scored) - len(unsupported)}/{len(scored)} claims supported"
                if scored
                else "no scoreable claims"
            )

        return CheckResult(
            check=self.name,
            passed=passed,
            score=0.0 if fabricated else support,
            detail=detail,
            evidence={
                "fabricated_citations": fabricated,
                "unsupported_claims": unsupported[:5],
                "citation_count": len(citations),
            },
        )
