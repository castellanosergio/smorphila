"""
Save data
"""

from PySide6.QtWidgets import QInputDialog, QMessageBox
from pathlib import Path
import re
import json
import os
import copy

from .project_store import definition_signature, load_project, save_project


def _save_to_unified_project(viewer, data, code):
    """Store one individual in the unified project and rename its image."""

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
        project["individuals"][code] = data
        save_project(project_path, project)
    except Exception:
        if image_path != original_path and image_path.is_file():
            image_path.rename(original_path)
        raise

    viewer.file_path = image_path
    viewer.setWindowTitle(
        f"{image_path.name} - Morphometric analysis - v. {viewer.__version__}"
    )


def save_data_json(viewer):
    if not viewer.nome_file:
        QMessageBox.critical(None, "Warning", "No image loaded")
        return

    code = viewer.code

    while True:
        # ask for code
        code, ok = QInputDialog.getText(
            None,
            "Enter individual info",
            "Code and date (CODE_NN_YYYY-MM-DD):",
            text=code,
        )
        if not ok:
            QMessageBox.information(
                None,
                "Warning",
                "Data not saved",
            )
            return

        if not code:
            QMessageBox.critical(None, "Warning", "The code is mandatory")
            continue

        if " " in code:
            QMessageBox.critical(None, "Warning", "The code cannot contain space")
            continue

        # check code
        if code.count("_") < 2:
            QMessageBox.critical(None, "Warning", "The code must contain almost 2 _ ")
            continue

        # Regex pattern for YYYY-MM-DD
        pattern = r"_\d{4}-\d{2}-\d{2}\b"

        if not re.search(pattern, code):
            QMessageBox.critical(
                None, "Warning", "The code does not contain a date in YYYY-MM-DD format"
            )
            continue

        break

    # ask for mass
    mass_value, ok = QInputDialog.getDouble(
        None,  # parent widget
        "Enter the mass value",  # dialog title
        "Mass (in g):",  # label text
        value=viewer.mass_value,  # default value
        minValue=0.0,  # minimum allowed value
        maxValue=100.0,  # maximum allowed value
        decimals=2,  # number of decimal places
    )

    if not ok:
        QMessageBox.information(
            None,
            "Warning",
            "Data not saved",
        )
        return

    data = {
        "mass_value": mass_value,
        "code": code,
        "angle_deg": viewer.angle_deg,
        "reference_axis_aligned": viewer.reference_axis_aligned,
        "coordinate_display_offset": viewer.coordinate_display_offset,
        "raw_to_display_transform": viewer.raw_to_display_transform,
        # "image_file_name": viewer.nome_file,
        # "directory_path": viewer.DIR_PNG,
        "scale": viewer.scale,
        "scale_unit": viewer.scale_unit,
        "landmarks_raw": copy.deepcopy(
            viewer.landmarks_raw
            if viewer.landmarks_raw is not None
            else viewer.landmarks
        ),
        "landmarks": viewer.landmarks,
        "semilandmarks": viewer.semilandmarks,
    }

    if getattr(viewer, "project_path", None) is not None:
        try:
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
