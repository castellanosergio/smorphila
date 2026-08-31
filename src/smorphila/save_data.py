"""
Save data
"""

from PySide6.QtWidgets import QInputDialog, QMessageBox
from pathlib import Path
import re
import json


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
        # "image_file_name": viewer.nome_file,
        # "directory_path": viewer.DIR_PNG,
        "scale": viewer.scale,
        "scale_unit": viewer.scale_unit,
        "landmarks": viewer.landmarks,
        "semilandmarks": viewer.semilandmarks,
    }

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
