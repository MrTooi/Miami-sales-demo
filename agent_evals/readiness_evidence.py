"""Deterministic post-processing for scheduled Agent OS readiness evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ALLOWED_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
EXPECTED_ACTOR = "MrTooi"


class EvidenceBindingError(ValueError):
    """Raised when runtime provenance cannot be bound safely into evidence."""


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile_fields(sanitized_profiles: dict[str, Any]) -> list[str]:
    agents = sanitized_profiles.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise EvidenceBindingError("sanitized team profiles are missing agents")

    field_sets: list[set[str]] = []
    for agent_id, profile in agents.items():
        if not isinstance(agent_id, str) or not agent_id:
            raise EvidenceBindingError("sanitized team profile has invalid agent id")
        if not isinstance(profile, dict) or not profile:
            raise EvidenceBindingError(f"sanitized team profile for {agent_id!r} is invalid")
        field_sets.append(set(profile))

    first = field_sets[0]
    if any(fields != first for fields in field_sets[1:]):
        raise EvidenceBindingError("sanitized team profiles do not expose a consistent field set")
    return sorted(first)


def augment_evidence(
    *,
    evidence_path: Path,
    blind_manifest_path: Path,
    sanitized_profiles_path: Path,
    model: str,
    effort: str,
    actor: str,
) -> dict[str, Any]:
    """Bind model/runtime/team provenance into the evidence file, fail closed."""
    model = model.strip()
    effort = effort.strip().lower()
    actor = actor.strip()

    if not model:
        raise EvidenceBindingError("model must be explicit and non-empty")
    if any(character.isspace() for character in model):
        raise EvidenceBindingError("model must not contain whitespace")
    if effort not in ALLOWED_EFFORTS:
        raise EvidenceBindingError(f"unsupported reasoning effort: {effort!r}")
    if actor != EXPECTED_ACTOR:
        raise EvidenceBindingError(
            f"scheduled readiness actor must be {EXPECTED_ACTOR!r}, received {actor!r}"
        )

    evidence = _load(evidence_path)
    blind_manifest = _load(blind_manifest_path)
    sanitized_profiles = _load(sanitized_profiles_path)
    if not isinstance(evidence, dict):
        raise EvidenceBindingError("evidence document must be an object")
    if not isinstance(blind_manifest, dict):
        raise EvidenceBindingError("blind manifest must be an object")
    source_profiles_hash = blind_manifest.get("source_team_profiles_sha256")
    if not isinstance(source_profiles_hash, str) or len(source_profiles_hash) != 64:
        raise EvidenceBindingError("blind manifest is missing source team-profile hash")

    fields = _profile_fields(sanitized_profiles)
    evidence.update(
        {
            "actor": actor,
            "model": model,
            "effort": effort,
            "source_team_profiles_sha256": source_profiles_hash,
            "sanitized_team_profiles_sha256": _sha256(sanitized_profiles_path),
            "blind_profile_fields": fields,
            "blind_profile_note": (
                "Pass 1 intentionally excludes repo paths/source metadata and hidden rubric fields."
            ),
        }
    )

    tmp_path = evidence_path.with_suffix(evidence_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(evidence_path)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--blind-manifest", required=True, type=Path)
    parser.add_argument("--sanitized-profiles", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--actor", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    augment_evidence(
        evidence_path=args.evidence,
        blind_manifest_path=args.blind_manifest,
        sanitized_profiles_path=args.sanitized_profiles,
        model=args.model,
        effort=args.effort,
        actor=args.actor,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
