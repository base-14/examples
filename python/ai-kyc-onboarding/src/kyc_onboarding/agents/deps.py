from datetime import date

from pydantic import BaseModel

from kyc_onboarding.models.enums import CaseFault


class AssessmentDeps(BaseModel):
    """Dependencies for the assessment agent, serialized across the activity boundary.
    `reference_date` is the workflow's `workflow.now()` date."""

    dsn: str
    reference_date: date
    fault: CaseFault | None = None
