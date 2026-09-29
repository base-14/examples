import importlib.util
import os


os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")

INSTALLED = {
    "strands": "strands",
    "google.adk": "adk",
    "agent_framework": "maf",
    "agents": "openai-agents",
}
FRAMEWORK_TESTS = {
    "strands": ["test_framework_strands.py", "test_api.py", "api_support.py", "scripted_model.py"],
    "google.adk": ["test_framework_adk.py"],
    "agent_framework": ["test_framework_maf.py"],
    "agents": ["test_framework_openai_agents.py"],
}


def _installed(package: str) -> bool:
    return (
        importlib.util.find_spec(package.split(".", maxsplit=1)[0]) is not None
        and importlib.util.find_spec(package) is not None
    )


collect_ignore = [
    name for package, names in FRAMEWORK_TESTS.items() if not _installed(package) for name in names
]
os.environ.setdefault(
    "FILING_FRAMEWORK", next(name for package, name in INSTALLED.items() if _installed(package))
)
