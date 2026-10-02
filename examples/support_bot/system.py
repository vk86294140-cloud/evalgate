"""A tiny stand-in for a retrieval-backed support bot.

It is deterministic and offline so the example runs anywhere. Set
SUPPORT_BOT_SLOPPY=1 to make it behave the way a real one does on a bad day -
confident, uncited, and occasionally quoting a policy that does not exist.
That is the behaviour the gate is supposed to catch.
"""

from __future__ import annotations

import os
import re
from typing import Any

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text.strip()) if s.strip()]


_STOP = frozenset("the and for are you your with that this have does from what when".split())


def _stem(word: str) -> str:
    for suffix in ("ing", "ies", "ed", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _terms(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in _STOP}


def _score(sentence: str, question: str) -> int:
    return len(_terms(question) & _terms(sentence))


def answer(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question", ""))
    context = payload.get("context", "")
    if isinstance(context, list):
        context = "\n".join(str(c) for c in context)

    sloppy = os.environ.get("SUPPORT_BOT_SLOPPY") == "1"
    candidates = _sentences(str(context))
    ranked = sorted(candidates, key=lambda s: _score(s, question), reverse=True)
    best = ranked[0] if ranked else ""
    hit = _score(best, question) if best else 0

    if hit == 0 and not sloppy:
        return {
            "answer": "I don't know based on the documents provided.",
            "citations": [],
            "confidence": 0.0,
            "abstained": True,
        }

    if sloppy:
        return {
            "answer": f"{best} Our policy also covers this in all regions, with no exceptions.",
            "citations": ["All regions are covered with no exceptions."],
            "confidence": 0.99,
            "abstained": False,
        }

    return {
        "answer": best,
        "citations": [best],
        "confidence": round(min(0.5 + 0.15 * hit, 0.98), 2),
        "abstained": False,
    }
