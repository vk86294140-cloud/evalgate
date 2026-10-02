from __future__ import annotations

import pytest

from evalgate.checks import build_check, known_checks, validate
from evalgate.dataset import Case

CONTEXT = (
    "Returns are accepted within 30 days of delivery. "
    "Refunds are issued to the original payment method within 5 business days."
)


def case(expect=None, context=CONTEXT):
    return Case(id="c1", input={"question": "how long?", "context": context}, expect=expect or {})


class TestSchema:
    def test_accepts_a_well_formed_output(self):
        check = build_check({"type": "schema", "schema": {"type": "object", "required": ["answer"]}})
        assert check.run(case(), {"answer": "hi"}).passed

    def test_reports_the_missing_field(self):
        check = build_check({"type": "schema", "schema": {"type": "object", "required": ["answer"]}})
        result = check.run(case(), {"citations": []})
        assert not result.passed
        assert "answer" in result.detail

    def test_booleans_are_not_numbers(self):
        errors = validate({"confidence": True}, {"properties": {"confidence": {"type": "number"}}})
        assert errors and "boolean" in errors[0]

    def test_bounds_and_enums(self):
        schema = {
            "properties": {
                "confidence": {"type": "number", "maximum": 1},
                "severity": {"enum": ["low", "high"]},
            }
        }
        errors = validate({"confidence": 1.5, "severity": "catastrophic"}, schema)
        assert len(errors) == 2

    def test_nested_arrays(self):
        schema = {"properties": {"citations": {"type": "array", "items": {"type": "string"}}}}
        assert validate({"citations": ["a", "b"]}, schema) == []
        assert validate({"citations": ["a", 7]}, schema)


class TestContains:
    def test_must_contain(self):
        check = build_check({"type": "contains"})
        assert check.run(case({"must_contain": ["30 days"]}), {"answer": CONTEXT}).passed

    def test_must_not_contain(self):
        check = build_check({"type": "contains"})
        result = check.run(case({"must_not_contain": ["90 days"]}), {"answer": "within 90 days"})
        assert not result.passed

    def test_regex(self):
        check = build_check({"type": "contains"})
        assert check.run(case({"matches": [r"\d+ days"]}), {"answer": "30 days"}).passed

    def test_partial_credit_in_the_score(self):
        check = build_check({"type": "contains"})
        result = check.run(case({"must_contain": ["30 days", "unicorn"]}), {"answer": "30 days"})
        assert not result.passed
        assert result.score == pytest.approx(0.5)

    def test_no_expectations_is_a_pass(self):
        assert build_check({"type": "contains"}).run(case(), {"answer": "anything"}).passed


class TestGrounding:
    def test_quoting_the_context_passes(self):
        check = build_check({"type": "grounding"})
        output = {
            "answer": "Returns are accepted within 30 days of delivery.",
            "citations": ["Returns are accepted within 30 days of delivery."],
        }
        assert check.run(case(), output).passed

    def test_a_fabricated_citation_fails_outright(self):
        check = build_check({"type": "grounding"})
        output = {
            "answer": "Returns are accepted within 90 days.",
            "citations": ["Returns are accepted within 90 days."],
        }
        result = check.run(case(), output)
        assert not result.passed
        assert result.score == 0.0
        assert result.evidence["fabricated_citations"]

    def test_an_uncited_answer_fails(self):
        check = build_check({"type": "grounding"})
        result = check.run(case(), {"answer": "Thirty days.", "citations": []})
        assert not result.passed
        assert "no citations" in result.detail

    def test_abstention_is_grounded_by_definition(self):
        check = build_check({"type": "grounding"})
        output = {"answer": "I don't know.", "citations": [], "abstained": True}
        assert check.run(case(), output).passed

    def test_unsupported_sentences_lower_the_score(self):
        check = build_check({"type": "grounding", "min_support": 0.99})
        output = {
            "answer": "Returns are accepted within 30 days of delivery. We also offer gift wrapping.",
            "citations": ["Returns are accepted within 30 days of delivery."],
        }
        result = check.run(case(), output)
        assert not result.passed
        assert result.evidence["unsupported_claims"]


class TestNumeric:
    def test_within_tolerance(self):
        check = build_check({"type": "numeric", "fields": ["confidence"], "tolerance": 0.05})
        assert check.run(case({"confidence": 0.8}), {"confidence": 0.83}).passed

    def test_outside_tolerance(self):
        check = build_check({"type": "numeric", "fields": ["confidence"], "tolerance": 0.05})
        assert not check.run(case({"confidence": 0.8}), {"confidence": 0.5}).passed

    def test_non_numeric_output_fails(self):
        check = build_check({"type": "numeric", "fields": ["confidence"]})
        assert not check.run(case({"confidence": 0.8}), {"confidence": "high"}).passed


def test_registry_lists_the_built_ins():
    assert {"schema", "contains", "grounding", "numeric"} <= set(known_checks())


def test_unknown_check_type_is_rejected():
    with pytest.raises(ValueError, match="unknown check type"):
        build_check({"type": "vibes"})
