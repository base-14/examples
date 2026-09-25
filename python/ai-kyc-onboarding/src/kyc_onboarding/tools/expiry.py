from datetime import date
from typing import Literal

from pydantic import BaseModel


ExpiryStatus = Literal["valid", "expired", "missing"]


class ExpiryCheck(BaseModel):
    """`status` is `missing` when no expiry date was given. `expired` is true only for a date
    before `reference_date`."""

    status: ExpiryStatus
    expired: bool
    expiry_date: date | None
    reference_date: date


def check_expiry(expiry_date: date | None, reference_date: date) -> ExpiryCheck:
    if expiry_date is None:
        return ExpiryCheck(
            status="missing", expired=False, expiry_date=None, reference_date=reference_date
        )
    expired = expiry_date < reference_date
    return ExpiryCheck(
        status="expired" if expired else "valid",
        expired=expired,
        expiry_date=expiry_date,
        reference_date=reference_date,
    )
