import json
import math
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# 1. READ THE SMORPHILA PROJECT
# ============================================================

def read_project(json_path):
    """
    Read a SMORPHILA project JSON file.

    The expected structure contains an "individuals" section:

        {
            "individuals": {
                "individual_1": {...},
                "individual_2": {...}
            }
        }
    """

    with open(json_path, "r", encoding="utf-8") as file:
        project = json.load(file)

    if "individuals" not in project:
        raise ValueError(
            "The selected file does not contain the 'individuals' section."
        )

    if not isinstance(project["individuals"], dict):
        raise ValueError(
            "The 'individuals' section must be a dictionary."
        )

    return project


# ============================================================
# 2. GET LANDMARK NAMES
# ============================================================

def get_landmark_names(project):
    """
    Return all landmark names found in the individuals.

    The order in which landmarks first appear in the project
    is preserved.
    """

    names = []

    for individual_data in project.get("individuals", {}).values():

        landmarks = individual_data.get("landmarks", {})

        for name in landmarks:

            if name not in names:
                names.append(name)

    return names


# ============================================================
# 3. READ LANDMARK COORDINATES
# ============================================================

def get_landmark_coordinates(individual_data, landmark_name):
    """
    Return the [x, y] coordinates of a landmark.

    The function supports the current SMORPHILA format:

        "SNOUT": {
            "coordinates": [x, y],
            "color": null
        }

    and also a possible compact future format:

        "SNOUT": [x, y]
    """

    landmarks = individual_data.get("landmarks", {})

    landmark = landmarks.get(landmark_name)

    if landmark is None:
        return None

    if isinstance(landmark, dict):
        coordinates = landmark.get("coordinates")

    elif isinstance(landmark, list):
        coordinates = landmark

    else:
        return None

    if coordinates is None:
        return None

    if len(coordinates) < 2:
        return None

    return coordinates


# ============================================================
# 4. EUCLIDEAN DISTANCE
# ============================================================

def euclidean_distance(point_1, point_2):
    """
    Calculate the Euclidean distance between two 2D points.

    d = sqrt((x2 - x1)^2 + (y2 - y1)^2)
    """

    x1 = point_1[0]
    y1 = point_1[1]

    x2 = point_2[0]
    y2 = point_2[1]

    difference_x = x2 - x1
    difference_y = y2 - y1

    squared_difference_x = difference_x * difference_x
    squared_difference_y = difference_y * difference_y

    distance = math.sqrt(
        squared_difference_x
        + squared_difference_y
    )

    return distance


# ============================================================
# 5. DEFINE ONE MEASUREMENT
# ============================================================

class MeasurementDialog(QDialog):
    """
    Dialog used to define one distance measurement.

    The user selects:
        - the first landmark
        - the second landmark
        - the name assigned to the measurement
    """

    def __init__(self, landmark_names, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Add distance")

        self.landmark_1_combo = QComboBox()
        self.landmark_2_combo = QComboBox()

        self.landmark_1_combo.addItems(landmark_names)
        self.landmark_2_combo.addItems(landmark_names)

        if len(landmark_names) > 1:
            self.landmark_2_combo.setCurrentIndex(1)

        self.name_edit = QLineEdit()

        form_layout = QFormLayout()

        form_layout.addRow(
            "First landmark:",
            self.landmark_1_combo,
        )

        form_layout.addRow(
            "Second landmark:",
            self.landmark_2_combo,
        )

        form_layout.addRow(
            "Distance name:",
            self.name_edit,
        )

        add_button = QPushButton("Add")
        cancel_button = QPushButton("Cancel")

        add_button.clicked.connect(
            self.accept_measurement
        )

        cancel_button.clicked.connect(
            self.reject
        )

        button_layout = QHBoxLayout()

        button_layout.addStretch()
        button_layout.addWidget(add_button)
        button_layout.addWidget(cancel_button)

        main_layout = QVBoxLayout(self)

        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_layout)


    def accept_measurement(self):
        """
        Validate the measurement before closing the dialog.
        """

        landmark_1 = self.landmark_1_combo.currentText()
        landmark_2 = self.landmark_2_combo.currentText()
        measurement_name = self.name_edit.text().strip()

        if landmark_1 == landmark_2:

            QMessageBox.warning(
                self,
                "Invalid distance",
                "Please select two different landmarks.",
            )

            return

        if measurement_name == "":

            QMessageBox.warning(
                self,
                "Missing name",
                "Please enter a name for the distance.",
            )

            return

        self.accept()


    def get_measurement(self):
        """
        Return the measurement as a dictionary.
        """

        return {
            "name": self.name_edit.text().strip(),
            "landmark_1": self.landmark_1_combo.currentText(),
            "landmark_2": self.landmark_2_combo.currentText(),
        }


# ============================================================
# 6. MAIN WINDOW
# ============================================================

class DistanceCalculator(QMainWindow):
    """
    Main window used to define landmark distances and export them.
    """

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "SMORPHILA - Landmark distances"
        )

        self.resize(
            800,
            600,
        )

        self.project = None
        self.json_path = None

        self.landmark_names = []
        self.measurements = []

        self.create_interface()


    # --------------------------------------------------------
    # CREATE INTERFACE
    # --------------------------------------------------------

    def create_interface(self):

        central_widget = QWidget()

        self.setCentralWidget(
            central_widget
        )

        main_layout = QVBoxLayout(
            central_widget
        )


        # ----------------------------------------------------
        # Project controls
        # ----------------------------------------------------

        project_layout = QHBoxLayout()

        self.project_label = QLabel(
            "No project loaded."
        )

        open_button = QPushButton(
            "Open project"
        )

        open_button.clicked.connect(
            self.open_project
        )

        project_layout.addWidget(
            self.project_label
        )

        project_layout.addStretch()

        project_layout.addWidget(
            open_button
        )

        main_layout.addLayout(
            project_layout
        )


        # ----------------------------------------------------
        # Available landmarks
        # ----------------------------------------------------

        landmarks_title = QLabel(
            "Available landmarks"
        )

        main_layout.addWidget(
            landmarks_title
        )

        self.landmark_list = QListWidget()

        main_layout.addWidget(
            self.landmark_list
        )


        # ----------------------------------------------------
        # Defined measurements
        # ----------------------------------------------------

        measurements_title = QLabel(
            "Defined distances"
        )

        main_layout.addWidget(
            measurements_title
        )

        self.measurement_list = QListWidget()

        main_layout.addWidget(
            self.measurement_list
        )


        # ----------------------------------------------------
        # Measurement buttons
        # ----------------------------------------------------

        measurement_button_layout = QHBoxLayout()

        self.add_button = QPushButton(
            "Add distance"
        )

        self.remove_button = QPushButton(
            "Remove selected distance"
        )

        self.add_button.setEnabled(False)
        self.remove_button.setEnabled(False)

        self.add_button.clicked.connect(
            self.add_measurement
        )

        self.remove_button.clicked.connect(
            self.remove_measurement
        )

        measurement_button_layout.addWidget(
            self.add_button
        )

        measurement_button_layout.addWidget(
            self.remove_button
        )

        measurement_button_layout.addStretch()

        main_layout.addLayout(
            measurement_button_layout
        )


        # ----------------------------------------------------
        # Export button
        # ----------------------------------------------------

        export_layout = QHBoxLayout()

        export_layout.addStretch()

        self.export_button = QPushButton(
            "Export distances"
        )

        self.export_button.setEnabled(False)

        self.export_button.clicked.connect(
            self.export_distances
        )

        export_layout.addWidget(
            self.export_button
        )

        main_layout.addLayout(
            export_layout
        )


    # --------------------------------------------------------
    # OPEN PROJECT
    # --------------------------------------------------------

    def open_project(self):

        json_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SMORPHILA project",
            "",
            "JSON files (*.json)",
        )

        if not json_path:
            return

        try:

            project = read_project(
                json_path
            )

            landmark_names = get_landmark_names(
                project
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Error",
                "Unable to open the project:\n\n"
                + str(error),
            )

            return


        if len(landmark_names) < 2:

            QMessageBox.warning(
                self,
                "Landmarks",
                "The project contains fewer than two landmarks.",
            )

            return


        self.project = project

        self.json_path = Path(
            json_path
        )

        self.landmark_names = landmark_names

        self.measurements = []


        # ----------------------------------------------------
        # Update project label
        # ----------------------------------------------------

        project_data = self.project.get(
            "project",
            {}
        )

        project_name = project_data.get(
            "name",
            self.json_path.stem,
        )

        self.project_label.setText(
            "Project: "
            + str(project_name)
        )


        # ----------------------------------------------------
        # Update landmark list
        # ----------------------------------------------------

        self.landmark_list.clear()

        for name in self.landmark_names:

            self.landmark_list.addItem(
                name
            )


        # ----------------------------------------------------
        # Reset measurement list
        # ----------------------------------------------------

        self.measurement_list.clear()

        self.add_button.setEnabled(True)
        self.remove_button.setEnabled(False)
        self.export_button.setEnabled(False)


    # --------------------------------------------------------
    # ADD MEASUREMENT
    # --------------------------------------------------------

    def add_measurement(self):

        if self.project is None:
            return

        dialog = MeasurementDialog(
            self.landmark_names,
            self,
        )

        result = dialog.exec()

        if result != QDialog.Accepted:
            return

        measurement = dialog.get_measurement()

        measurement_name = measurement["name"]


        # ----------------------------------------------------
        # Do not allow duplicate names
        # ----------------------------------------------------

        for existing_measurement in self.measurements:

            if existing_measurement["name"] == measurement_name:

                QMessageBox.warning(
                    self,
                    "Duplicate name",
                    "A distance with this name already exists.",
                )

                return


        self.measurements.append(
            measurement
        )

        self.update_measurement_list()


    # --------------------------------------------------------
    # REMOVE MEASUREMENT
    # --------------------------------------------------------

    def remove_measurement(self):

        current_row = self.measurement_list.currentRow()

        if current_row < 0:
            return

        del self.measurements[current_row]

        self.update_measurement_list()


    # --------------------------------------------------------
    # UPDATE MEASUREMENT LIST
    # --------------------------------------------------------

    def update_measurement_list(self):

        self.measurement_list.clear()

        for measurement in self.measurements:

            text = (
                measurement["name"]
                + ": "
                + measurement["landmark_1"]
                + " - "
                + measurement["landmark_2"]
            )

            item = QListWidgetItem(
                text
            )

            self.measurement_list.addItem(
                item
            )


        has_measurements = (
            len(self.measurements) > 0
        )

        self.remove_button.setEnabled(
            has_measurements
        )

        self.export_button.setEnabled(
            has_measurements
        )


    # --------------------------------------------------------
    # EXPORT DISTANCES
    # --------------------------------------------------------

    def export_distances(self):

        if self.project is None:
            return

        if len(self.measurements) == 0:

            QMessageBox.warning(
                self,
                "Export",
                "No distances have been defined.",
            )

            return


        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save distance table",
            "",
            "Text files (*.txt)",
        )

        if not output_path:
            return

        if not output_path.lower().endswith(
            ".txt"
        ):

            output_path += ".txt"


        try:

            self.write_distance_table(
                output_path
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Export error",
                "Unable to export the distances:\n\n"
                + str(error),
            )

            return


        QMessageBox.information(
            self,
            "Export",
            "Distance table exported successfully.",
        )


    # --------------------------------------------------------
    # WRITE TXT TABLE
    # --------------------------------------------------------

    def write_distance_table(self, output_path):
        """
        Write a wide TXT table.

        Rows = individuals
        Columns = named distances
        """

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:


            # ------------------------------------------------
            # Header
            # ------------------------------------------------

            header = [
                "individual"
            ]

            for measurement in self.measurements:

                header.append(
                    measurement["name"]
                )

            file.write(
                "\t".join(header)
                + "\n"
            )


            # ------------------------------------------------
            # One row per individual
            # ------------------------------------------------

            for code, individual_data in (
                self.project["individuals"].items()
            ):

                row = [
                    str(code)
                ]


                # --------------------------------------------
                # Calculate each selected distance
                # --------------------------------------------

                for measurement in self.measurements:

                    landmark_1 = measurement[
                        "landmark_1"
                    ]

                    landmark_2 = measurement[
                        "landmark_2"
                    ]


                    point_1 = get_landmark_coordinates(
                        individual_data,
                        landmark_1,
                    )

                    point_2 = get_landmark_coordinates(
                        individual_data,
                        landmark_2,
                    )


                    # ----------------------------------------
                    # Missing landmark
                    # ----------------------------------------

                    if (
                        point_1 is None
                        or point_2 is None
                    ):

                        row.append(
                            "NA"
                        )

                        continue


                    # ----------------------------------------
                    # Euclidean distance
                    # ----------------------------------------

                    distance = euclidean_distance(
                        point_1,
                        point_2,
                    )

                    row.append(
                        str(distance)
                    )


                file.write(
                    "\t".join(row)
                    + "\n"
                )


# ============================================================
# 7. START APPLICATION
# ============================================================

def run():

    app = QApplication(
        sys.argv
    )

    window = DistanceCalculator()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":

    run()
