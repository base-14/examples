from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field


if TYPE_CHECKING:
    from kyc_onboarding.models.documents import (
        ExtractedIdFields,
        ExtractedProofOfAddressFields,
        ExtractedRegistrationCertificateFields,
    )


class IdentityCheck(BaseModel):
    match: bool
    mismatches: list[str] = Field(default_factory=list)


def _normalize(value: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", value.lower())
    return " ".join(cleaned.split())


def _normalize_name(value: str) -> str:
    return " ".join(sorted(_normalize(value).split()))


def compare_identity(
    id_fields: ExtractedIdFields | None = None,
    proof_of_address_fields: ExtractedProofOfAddressFields | None = None,
    registration_certificate_fields: ExtractedRegistrationCertificateFields | None = None,
) -> IdentityCheck:
    mismatches: list[str] = []

    names: dict[str, str] = {}
    if id_fields is not None:
        names["id"] = id_fields.full_name
    if registration_certificate_fields is not None:
        names["registration_certificate"] = (
            registration_certificate_fields.authorized_representative
        )
    elif proof_of_address_fields is not None:
        names["proof_of_address"] = proof_of_address_fields.account_holder

    normalized_names = {source: _normalize_name(name) for source, name in names.items()}
    if len(set(normalized_names.values())) > 1:
        mismatches.append("name mismatch across " + ", ".join(sorted(normalized_names)))

    dates_of_birth = {}
    if id_fields is not None:
        dates_of_birth["id"] = id_fields.date_of_birth
    if (
        registration_certificate_fields is not None
        and registration_certificate_fields.authorized_representative_date_of_birth is not None
    ):
        dates_of_birth["registration_certificate"] = (
            registration_certificate_fields.authorized_representative_date_of_birth
        )

    if len(set(dates_of_birth.values())) > 1:
        mismatches.append("date of birth mismatch across " + ", ".join(sorted(dates_of_birth)))

    declared_address: str | None = None
    declared_source: str | None = None
    if registration_certificate_fields is not None:
        declared_address = registration_certificate_fields.address
        declared_source = "registration_certificate"
    elif id_fields is not None and id_fields.declared_address is not None:
        declared_address = id_fields.declared_address
        declared_source = "id"

    if (
        declared_address is not None
        and proof_of_address_fields is not None
        and _normalize(declared_address) != _normalize(proof_of_address_fields.address)
    ):
        mismatches.append(f"address on {declared_source} does not match proof_of_address")

    return IdentityCheck(match=not mismatches, mismatches=mismatches)
