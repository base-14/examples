from pathlib import Path

from kyc_onboarding.models.documents import SubmittedDocument
from kyc_onboarding.models.enums import DocumentType


FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"


def list_fixture_sets() -> list[str]:
    return sorted(entry.name for entry in FIXTURES_ROOT.iterdir() if entry.is_dir())


def load_fixture_set(name: str) -> list[SubmittedDocument]:
    scenario_dir = FIXTURES_ROOT / name
    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"no fixture set named {name!r} under {FIXTURES_ROOT}")

    documents = []
    for document_file in sorted(scenario_dir.glob("*.txt")):
        document_type = DocumentType(document_file.stem)
        documents.append(
            SubmittedDocument(
                document_type=document_type,
                raw_text=document_file.read_text(encoding="utf-8").strip(),
            )
        )
    return documents
