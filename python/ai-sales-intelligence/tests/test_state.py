"""Tests for state models."""

import pytest
from pydantic import ValidationError

from sales_intelligence.state import (
    AgentState,
    EmailDraft,
    EnrichedData,
    EvaluationResult,
    ProspectData,
    ScoredProspect,
)


class TestProspectData:
    def test_create_prospect(self):
        prospect = ProspectData(
            connection_id="123",
            first_name="John",
            last_name="Doe",
            company="Acme Inc",
            position="CTO",
        )
        assert prospect.first_name == "John"
        assert prospect.email is None

    def test_prospect_with_email(self):
        prospect = ProspectData(
            connection_id="123",
            first_name="John",
            last_name="Doe",
            company="Acme Inc",
            position="CTO",
            email="john@acme.com",
        )
        assert prospect.email == "john@acme.com"


class TestEnrichedData:
    def test_default_values(self):
        enriched = EnrichedData()
        assert enriched.industry is None
        assert enriched.tech_stack == []
        assert enriched.confidence == 0.0

    def test_confidence_bounds(self):
        enriched = EnrichedData(confidence=0.5)
        assert enriched.confidence == 0.5

        with pytest.raises(ValidationError):
            EnrichedData(confidence=1.5)

        with pytest.raises(ValidationError):
            EnrichedData(confidence=-0.1)


class TestScoredProspect:
    def test_score_bounds(self):
        prospect = ProspectData(
            connection_id="123",
            first_name="John",
            last_name="Doe",
            company="Acme",
            position="CTO",
        )
        enrichment = EnrichedData()

        scored = ScoredProspect(
            prospect=prospect,
            enrichment=enrichment,
            icp_score=75,
            reasoning="Good fit",
        )
        assert scored.icp_score == 75

        with pytest.raises(ValidationError):
            ScoredProspect(
                prospect=prospect,
                enrichment=enrichment,
                icp_score=150,
                reasoning="Invalid",
            )


class TestEmailDraft:
    def test_create_draft(self):
        draft = EmailDraft(
            prospect_id="123",
            subject="Quick question",
            body="Hi John...",
        )
        assert draft.subject == "Quick question"
        assert draft.body == "Hi John..."


class TestEvaluationResult:
    def test_passed_evaluation(self):
        result = EvaluationResult(
            draft_id="123",
            quality_score=80,
            passed=True,
            feedback="Good email",
        )
        assert result.passed is True
        assert result.issues == []

    def test_failed_evaluation(self):
        result = EvaluationResult(
            draft_id="123",
            quality_score=40,
            passed=False,
            feedback="Needs improvement",
            issues=["Too generic", "No personalization"],
        )
        assert result.passed is False
        assert len(result.issues) == 2


class TestAgentState:
    def test_default_state(self):
        state = AgentState(campaign_id="test-123")
        assert state.campaign_id == "test-123"
        assert state.prospects == []
        assert state.current_step == "research"
        assert state.score_threshold == 50
        assert state.quality_threshold == 60

    def test_state_with_data(self):
        prospect = ProspectData(
            connection_id="123",
            first_name="John",
            last_name="Doe",
            company="Acme",
            position="CTO",
        )
        state = AgentState(
            campaign_id="test-123",
            target_keywords=["SaaS", "AI"],
            prospects=[prospect],
        )
        assert len(state.prospects) == 1
        assert state.target_keywords == ["SaaS", "AI"]

    def test_state_copy_update(self):
        state = AgentState(campaign_id="test-123")
        new_state = state.model_copy(update={"current_step": "enrich"})
        assert state.current_step == "research"
        assert new_state.current_step == "enrich"
