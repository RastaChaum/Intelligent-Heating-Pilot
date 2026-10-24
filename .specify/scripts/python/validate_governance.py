#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REVIEW_STATUSES = {"pending", "in_review", "approved", "changes_requested"}

BODY_REQUIREMENTS = {
    "spec": [
        "## User Scenarios & Testing *(mandatory)*",
        "## Requirements *(mandatory)*",
        "### Workflow Requirements *(mandatory)*",
        "### Documentation Requirements *(mandatory)*",
        "## Success Criteria *(mandatory)*",
    ],
    "plan": ["## Constitution Check"],
    "tasks": ["## Phase N: Critical Review & Validation"],
}

STAGE_DOCS = {
    "spec": ["spec"],
    "plan": ["spec", "plan"],
    "tasks": ["spec", "plan", "tasks"],
    "implement": ["spec", "plan", "tasks"],
    "final": ["spec", "plan", "tasks"],
}

DOC_PATHS = {
    "spec": "spec.md",
    "plan": "plan.md",
    "tasks": "tasks.md",
}


@dataclass
class ValidationMessage:
    level: str
    code: str
    message: str
    path: str | None = None


class ValidationError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate speckit governance metadata")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--feature-dir", required=True)
    parser.add_argument("--stage", required=True, choices=sorted(STAGE_DOCS))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValidationError(f"Missing required file: {path}") from exc


def parse_front_matter(text: str, path: Path) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValidationError(f"Missing YAML front matter in {path}")

    lines = text.splitlines()
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break

    if end_index is None:
        raise ValidationError(f"Unterminated YAML front matter in {path}")

    metadata: dict[str, str] = {}
    for raw_line in lines[1:end_index]:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in raw_line:
            raise ValidationError(f"Invalid YAML front matter line in {path}: {raw_line}")
        key, value = raw_line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata


def extract_body(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1 :])
    return text


def agent_file_exists(repo_root: Path, agent_name: str) -> bool:
    return (repo_root / ".github" / "agents" / f"{agent_name}.agent.md").is_file()


def add_message(
    messages: list[ValidationMessage],
    level: str,
    code: str,
    message: str,
    path: Path | None = None,
) -> None:
    messages.append(ValidationMessage(level, code, message, str(path) if path else None))


def validate_metadata(
    metadata: dict[str, str],
    body: str,
    doc_kind: str,
    path: Path,
    repo_root: Path,
) -> list[ValidationMessage]:
    messages: list[ValidationMessage] = []

    required_keys = ["stage", "producer_agent", "critical_reviewer_agent", "review_status"]
    if doc_kind == "spec":
        required_keys.extend(
            [
                "plan_reviewer_agent",
                "tasks_reviewer_agent",
                "implementation_reviewer_agent",
            ]
        )
    if doc_kind == "tasks":
        required_keys.extend(["implementation_producer_agent", "implementation_reviewer_agent"])

    for key in required_keys:
        if not metadata.get(key):
            add_message(
                messages, "error", "missing-metadata", f"Missing required metadata '{key}'", path
            )

    producer = metadata.get("producer_agent")
    reviewer = metadata.get("critical_reviewer_agent")
    if producer and reviewer and producer == reviewer:
        add_message(
            messages,
            "error",
            "same-agent",
            "producer_agent and critical_reviewer_agent must be different",
            path,
        )

    status = metadata.get("review_status", "")
    if status and status not in REVIEW_STATUSES:
        add_message(
            messages, "error", "invalid-review-status", f"Invalid review_status '{status}'", path
        )

    for key, value in metadata.items():
        if key.endswith("agent") and value and not agent_file_exists(repo_root, value):
            add_message(
                messages,
                "error",
                "missing-agent-file",
                f"Referenced agent '{value}' does not exist",
                path,
            )

    expected_stage = {
        "spec": "specification",
        "plan": "planning",
        "tasks": "task-generation",
    }[doc_kind]
    actual_stage = metadata.get("stage")
    if actual_stage and actual_stage != expected_stage:
        add_message(
            messages,
            "error",
            "invalid-stage",
            f"Expected stage '{expected_stage}', found '{actual_stage}'",
            path,
        )

    for heading in BODY_REQUIREMENTS[doc_kind]:
        if heading not in body:
            add_message(
                messages, "error", "missing-section", f"Missing required section '{heading}'", path
            )

    if doc_kind == "tasks":
        implementation_producer = metadata.get("implementation_producer_agent")
        implementation_reviewer = metadata.get("implementation_reviewer_agent")
        if (
            implementation_producer
            and implementation_reviewer
            and implementation_producer == implementation_reviewer
        ):
            add_message(
                messages,
                "error",
                "self-review-implementation",
                "Implementation producer and reviewer must be different",
                path,
            )
        if implementation_reviewer != "speckit.review":
            add_message(
                messages,
                "warning",
                "unexpected-implementation-reviewer",
                "implementation_reviewer_agent is not speckit.review",
                path,
            )
        review_task_pattern = re.compile(r"(?im)^- \[[ xX]\] .*critical review")
        if not review_task_pattern.search(body):
            add_message(
                messages,
                "warning",
                "critical-review-task-not-found",
                "Tasks file should include an explicit critical review checklist item",
                path,
            )

    return messages


def validate_stage(repo_root: Path, feature_dir: Path, stage: str) -> list[ValidationMessage]:
    messages: list[ValidationMessage] = []
    for doc_kind in STAGE_DOCS[stage]:
        path = feature_dir / DOC_PATHS[doc_kind]
        text = load_text(path)
        metadata = parse_front_matter(text, path)
        body = extract_body(text)
        messages.extend(validate_metadata(metadata, body, doc_kind, path, repo_root))
    return messages


def emit(messages: list[ValidationMessage], json_mode: bool) -> int:
    has_errors = any(message.level == "error" for message in messages)
    if json_mode:
        payload = {"ok": not has_errors, "messages": [message.__dict__ for message in messages]}
        print(json.dumps(payload, indent=2))
        return 1 if has_errors else 0

    if not messages:
        print("[governance] OK")
        return 0

    for message in messages:
        prefix = "ERROR" if message.level == "error" else "WARN"
        location = f" [{message.path}]" if message.path else ""
        print(f"[governance] {prefix} {message.code}{location}: {message.message}")
    return 1 if has_errors else 0


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    feature_dir = Path(args.feature_dir)
    try:
        messages = validate_stage(repo_root, feature_dir, args.stage)
    except ValidationError as exc:
        return emit([ValidationMessage("error", "validation-failed", str(exc))], args.json)
    return emit(messages, args.json)


if __name__ == "__main__":
    sys.exit(main())
