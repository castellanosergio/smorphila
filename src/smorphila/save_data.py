"""
Save data
"""

from PySide6.QtWidgets import QMessageBox
from pathlib import Path
import json
import os

from .project_store import definition_signature, load_project, save_project


def _record_codes_for_image(project, project_path, image_path, code):
    """Return records that have the code or refer to the opened image."""

    matches = {code} if code in project["individuals"] else set()
    try:
        resolved_image = image_path.resolve()
    except OSError:
        return matches
    for existing_code, individual in project["individuals"].items():
        if not isinstance(individual, dict):
            continue
        stored_path = individual.get("image_path")
        if not isinstance(stored_path, str):
            continue
        try:
            if (project_path.parent / stored_path).resolve() == resolved_image:
                matches.add(existing_code)
        except OSError:
            continue
    return matches


def _save_to_unified_project(viewer, data, code):
    """Store one individual in the unified project under the image filename."""

    project_path = viewer.project_path
    original_path = viewer.file_path
    image_path = original_path.parent / Path(code).with_suffix(".jpg")
    if image_path != original_path and image_path.exists():
        raise ValueError(f"The image file already exists: {image_path.name}")

    if image_path != original_path:
        original_path.rename(image_path)
    try:
        project = load_project(project_path)
        data["image_path"] = os.path.relpath(
            image_path, start=project_path.parent
        ).replace("\\", "/")
        data["definition_signature"] = definition_signature(project["definitions"])
        for existing_code in _record_codes_for_image(
            project, project_path, image_path, code
        ):
            if existing_code != code:
                del project["individuals"][existing_code]
        project["individuals"][code] = data
        save_project(project_path, project)
    except Exception:
        if image_path != original_path and image_path.is_file():
            image_path.rename(original_path)
        raise

    viewer.file_path = image_path
    viewer.code = code
    viewer.setWindowTitle(
        f"{image_path.name} - Morphometric analysis - v. {viewer.__version__}"
    )


def save_data_json(viewer):
    if not viewer.nome_file:
        QMessageBox.critical(None, "Warning", "No image loaded")
        return

    code = viewer.file_path.stem.strip()
    if not code or code in {".", ".."}:
        QMessageBox.critical(None, "Warning", "The image filename is invalid.")
        return

    data = {
        "code": code,
        # "image_file_name": viewer.nome_file,
        # "directory_path": viewer.DIR_PNG,
        "scale": viewer.scale,
        "scale_unit": viewer.scale_unit,
        "landmarks": viewer.landmarks_raw
        if viewer.landmarks_raw is not None
        else viewer.landmarks,
        "semilandmarks": viewer.semilandmarks,
    }

    if getattr(viewer, "project_path", None) is not None:
        try:
            project = load_project(viewer.project_path)
            existing_codes = _record_codes_for_image(
                project, viewer.project_path, viewer.file_path, code
            )
            if existing_codes:
                answer = QMessageBox.question(
                    None,
                    "Overwrite data",
                    "This image has already been processed. Overwrite its saved data?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            _save_to_unified_project(viewer, data, code)
            QMessageBox.information(
                None,
                "Information",
                f"Data saved to {viewer.project_path.name}",
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(None, "Warning", str(error))
        return

    json_file_path = viewer.file_path.parent / Path(code).with_suffix(".json")

    if json_file_path.exists():
        answer = QMessageBox.question(
            None,
            "Overwrite data",
            "This image has already been processed. Overwrite its saved data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

    try:
        with open(json_file_path, "w") as f_in:
            json.dump(data, f_in, indent=0)

        # rename image file
        viewer.file_path.rename(
            viewer.file_path.parent / Path(code).with_suffix(".jpg")
        )

        if viewer.file_path.with_suffix(".json") != json_file_path:
            if viewer.file_path.is_file():
                viewer.file_path.with_suffix(".json").unlink()

        # update original file path
        viewer.file_path = Path(
            viewer.file_path.parent / Path(code).with_suffix(".jpg")
        )
        viewer.code = code
        viewer.setWindowTitle(
            f"{viewer.file_path.name} - Morphometric analysis - v. {viewer.__version__}"
        )

        QMessageBox.information(
            None,
            "Information",
            f"Data saved in {json_file_path}",
        )

    except Exception as e:
        QMessageBox.critical(None, "Warning", str(e))
