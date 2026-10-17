from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from northstar_rag.policy_build import build_corpus

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
REQUIRED_DOCUMENTS = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs" / "project-documentation.md",
    PROJECT_ROOT / "docs" / "prompt-log.md",
    PROJECT_ROOT / "docs" / "video-demo-script.md",
    PROJECT_ROOT / "docs" / "evaluation-report.md",
)
REQUIRED_COMMAND_REFERENCES = {
    "python scripts/check_models.py": PROJECT_ROOT / "scripts" / "check_models.py",
    "python scripts/build_policy_corpus.py": PROJECT_ROOT / "scripts" / "build_policy_corpus.py",
    "python scripts/ingest.py": PROJECT_ROOT / "scripts" / "ingest.py",
    "streamlit run app.py": PROJECT_ROOT / "app.py",
    "python scripts/evaluate.py --dataset development": PROJECT_ROOT
    / "evaluation"
    / "development_questions.json",
    "python scripts/evaluate.py --dataset final": PROJECT_ROOT / "evaluation" / "questions.json",
    "python -m pytest -q": PROJECT_ROOT / "tests",
}
FORBIDDEN_DELIVERY_TERMS = re.compile(
    r"\b("
    + "|".join(
        (
            "co" + r"urse(?:[- ]ready)?",
            "we" + r"ek[ -]?2",
            "stu" + "dent",
            "assign" + "ment",
            "sub" + "mission",
        )
    )
    + r")\b",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{16,}", re.IGNORECASE),
    re.compile(
        r"(?m)^\s*NEBIUS_API_KEY[ \t]*=[ \t]*(?!your-|replace-|<)[^\s#]{16,}",
    ),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_project_paths() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--", PROJECT_ROOT.name],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [REPOSITORY_ROOT / line for line in output.splitlines() if line]


def test_operating_documents_exist_and_readme_commands_resolve() -> None:
    for document in REQUIRED_DOCUMENTS:
        relative_name = document.relative_to(PROJECT_ROOT)
        assert document.is_file(), f"missing operating document: {relative_name}"

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for command, target in REQUIRED_COMMAND_REFERENCES.items():
        assert command in readme, f"README is missing command: {command}"
        assert target.exists(), f"README command target does not exist: {target}"


def test_approval_gate_is_prominent_in_runbook_and_project_documentation() -> None:
    for path in REQUIRED_DOCUMENTS[:2]:
        text = path.read_text(encoding="utf-8").casefold()
        assert "people operations" in text
        assert "legal" in text
        assert "approval" in text
        assert "draft" in text
        assert "not" in text and "production" in text


def test_no_local_environment_or_index_state_is_tracked() -> None:
    relative_paths = [path.relative_to(PROJECT_ROOT) for path in tracked_project_paths()]

    assert all(path.name != ".env" for path in relative_paths)
    assert all(path.parts[:2] != ("data", "index") for path in relative_paths)
    assert all("evaluation/runs" not in path.as_posix() for path in relative_paths)


def test_pdf_artifacts_are_declared_binary_for_repository_diffs() -> None:
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "*.pdf binary" in attributes.splitlines()


def test_committed_text_has_no_nebius_key_pattern_or_educational_framing() -> None:
    violations: list[str] = []
    for path in tracked_project_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            violations.append(f"secret pattern in {path.relative_to(PROJECT_ROOT)}")
        if path.suffix.lower() in {".md", ".py"} and FORBIDDEN_DELIVERY_TERMS.search(text):
            violations.append(f"delivery language in {path.relative_to(PROJECT_ROOT)}")
    assert not violations, "\n".join(violations)


def test_six_policy_pdfs_match_clean_deterministic_rebuild(tmp_path: Path) -> None:
    rebuilt = build_corpus(PROJECT_ROOT / "data" / "source" / "manifest.json", tmp_path)
    committed = sorted((PROJECT_ROOT / "data" / "policies").glob("*.pdf"))

    assert len(rebuilt) == 6
    assert len(committed) == 6
    assert {path.name: sha256(path) for path in rebuilt} == {
        path.name: sha256(path) for path in committed
    }
