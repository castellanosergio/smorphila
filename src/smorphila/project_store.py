"""Read and write the unified SMORPHILA project file."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib as pl
import tempfile


PROJECT_FORMAT = "SMORPHILA_PROJECT"
PROJECT_VERSION = "1.0"


def definition_signature(definitions: dict) -> str:
    """Return a stable fingerprint for a project definition."""

    payload = json.dumps(definitions, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def inconsistent_individuals(project: dict) -> dict[str, list[str]]:
    """Return records that do not match the current project definitions."""

    definitions = project["definitions"]
    expected_signature = definition_signature(definitions)
    expected_landmarks = definitions.get("landmarks", {})
    expected_curves = definitions.get("curves", {})
    if not isinstance(expected_landmarks, dict):
        expected_landmarks = {}
    if not isinstance(expected_curves, dict):
        expected_curves = {}
    inconsistent = {}

    for code, individual in project["individuals"].items():
        reasons = []
        if individual.get("definition_signature") != expected_signature:
            if "definition_signature" in individual:
                reasons.append("project definitions changed since acquisition")
            else:
                reasons.append("definition revision was not recorded")

        landmarks = individual.get("landmarks", {})
        if not isinstance(landmarks, dict):
            reasons.append("landmarks are missing or invalid")
        else:
            for name in expected_landmarks:
                landmark = landmarks.get(name)
                coordinates = (
                    landmark.get("coordinates") if isinstance(landmark, dict) else None
                )
                if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 2:
                    reasons.append(f"missing landmark '{name}'")

        semilandmarks = individual.get("semilandmarks", {})
        if not isinstance(semilandmarks, dict):
            semilandmarks = {}
        for name, curve in expected_curves.items():
            if not isinstance(curve, dict):
                reasons.append(f"invalid curve definition '{name}'")
                continue
            saved_curve = semilandmarks.get(name)
            if not isinstance(saved_curve, dict):
                reasons.append(f"missing curve '{name}'")
                continue
            expected_anchors = [
                curve.get("start_landmark"),
                curve.get("end_landmark"),
            ]
            if saved_curve.get("landmarks") != expected_anchors:
                reasons.append(f"curve anchors changed for '{name}'")
            coordinates = saved_curve.get("coordinates")
            expected_count = curve.get("point_count")
            if not isinstance(coordinates, list):
                reasons.append(f"curve coordinates are invalid for '{name}'")
            elif isinstance(expected_count, int) and len(coordinates) != expected_count + 1:
                reasons.append(f"curve point count changed for '{name}'")

        removed_curves = set(semilandmarks) - set(expected_curves)
        for name in sorted(removed_curves):
            reasons.append(f"curve '{name}' is no longer defined")
        if reasons:
            inconsistent[str(code)] = reasons

    return inconsistent


def create_project(name: str) -> dict:
    """Return an empty unified project with the supplied display name."""

    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "project": {"name": name},
        "definitions": {},
        "individuals": {},
    }


def load_project(path: pl.Path) -> dict:
    """Load and minimally validate a unified project file."""

    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read project: {error}") from error
    if not isinstance(project, dict):
        raise ValueError("The project root must be an object")
    if project.get("format") != PROJECT_FORMAT:
        raise ValueError("The selected file is not a SMORPHILA project")
    if not isinstance(project.get("project"), dict):
        raise ValueError("project must be an object")
    if not isinstance(project.get("definitions"), dict):
        raise ValueError("definitions must be an object")
    if not isinstance(project.get("individuals"), dict):
        raise ValueError("individuals must be an object")
    return project


def save_project(path: pl.Path, project: dict):
    """Atomically save a unified project without risking a partial JSON file."""

    if not isinstance(project, dict):
        raise ValueError("The project root must be an object")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp", dir=path.parent
    )
    temporary_path = pl.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(project, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_path.replace(path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise ValueError(f"Could not save project: {error}") from error
