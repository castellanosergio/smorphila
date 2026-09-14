import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# 1. READ JSON PROJECT
# ============================================================

def read_project(json_path):
    """
    Read a single SMORPHILA project JSON file.

    Expected structure:

    {
        "format": "SMORPHILA_PROJECT",
        "version": "1.0",
        "project": {...},
        "definitions": {...},
        "individuals": {
            "individual_code_1": {...},
            "individual_code_2": {...}
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
# 2. AVAILABLE INDIVIDUALS, LANDMARKS, AND SEMILANDMARKS
# ============================================================

def get_individuals(project):
    """ 
    Returns the codes of the individuals present in the project.
    Preserves their order in the JSON file.
    """

    return list(project.get("individuals", {}).keys())


def get_landmarks(project):
    """
    Returns all landmark names found in the individuals.
    Preserves the order in which they first appear in the project.
    """

    names = []

    for individual_data in project.get("individuals", {}).values():

        landmarks = individual_data.get("landmarks", {})

        for nome in landmarks:

            if nome not in names:
                names.append(nome)

    return names


def get_semilandmarks(project):
    """
    Returns all semilandmark names found in the individuals.
    Preserves the order in which they first appear in the project.
    """

    names = []

    for individual_data in project.get("individuals", {}).values():

        semilandmarks = individual_data.get(
            "semilandmarks",
            {}
        )

        for nome in semilandmarks:

            if nome not in names:
                names.append(nome)

    return names


# ============================================================
# 3. READ COORDINATES
# ============================================================

def get_landmark_coordinates(individual_data, landmark_name):
    """
    Legge le coordinates di un landmark.

    Compatibile con il formato attuale:

        "landmarks": {
            "SNOUT": {
                "coordinates": [x, y],
                "color": null
            }
        }
    """

    landmarks = individual_data.get("landmarks", {})

    landmark = landmarks.get(landmark_name)

    if landmark is None:
        return None

    # Format attuale:
    # "SNOUT": {"coordinates": [x, y], "color": null}
    if isinstance(landmark, dict):

        coordinates = landmark.get("coordinates")

    # Future compatibility:
    # "SNOUT": [x, y]
    elif isinstance(landmark, list):

        coordinates = landmark

    else:
        return None


    if coordinates is None:
        return None

    if len(coordinates) < 2:
        return None

    return coordinates


def get_semilandmark_coordinates(
    individual_data,
    group_name,
):
    """
    Legge le coordinates di un gruppo di semilandmark.

    Compatibile con il formato attuale:

        "semilandmarks": {
            "MUSO_Sx": {
                "landmarks": [...],
                "nsemilandmarks": [16],
                "coordinates": [...]
            }
        }

    and with a possible more compact future format:

        "semilandmarks": {
            "MUSO_Sx": [...]
        }
    """

    semilandmarks = individual_data.get(
        "semilandmarks",
        {}
    )

    gruppo = semilandmarks.get(group_name)

    if gruppo is None:
        return None


    # Format attuale
    if isinstance(gruppo, dict):

        coordinates = gruppo.get("coordinates")


    # Possible future format
    elif isinstance(gruppo, list):

        coordinates = gruppo


    else:

        return None


    if coordinates is None:
        return None

    return coordinates


# ============================================================
# 4. BUILD POINT LIST
# ============================================================

def get_individual_points(
    individual_data,
    selected_landmarks,
    selected_semilandmarks,
):
    """
    Build a list:

        (point_name, x, y)

    first containing the selected landmarks,
    followed by the selected semilandmark groups.
    """

    points = []


    # --------------------------------------------------------
    # Landmarks
    # --------------------------------------------------------

    for nome in selected_landmarks:

        coordinates = get_landmark_coordinates(
            individual_data,
            nome,
        )

        if coordinates is None:
            continue

        x = coordinates[0]
        y = coordinates[1]

        points.append(
            (nome, x, y)
        )


    # --------------------------------------------------------
    # Semilandmarks
    # --------------------------------------------------------

    for group_name in selected_semilandmarks:

        group_coordinates = get_semilandmark_coordinates(
            individual_data,
            group_name,
        )

        if group_coordinates is None:
            continue

        for number, coordinates in enumerate(
            group_coordinates,
            start=1,
        ):

            if coordinates is None:
                continue

            if len(coordinates) < 2:
                continue

            x = coordinates[0]
            y = coordinates[1]

            point_name = (
                group_name
                + "_"
                + str(number)
            )

            points.append(
                (point_name, x, y)
            )

    return points


# ============================================================
# 5. COMPLETENESS CHECK
# ============================================================

def check_individual(
    individual_data,
    selected_landmarks,
    selected_semilandmarks,
):
    """
    Check whether an individual contains all selected points.
    """

    problems = []


    # --------------------------------------------------------
    # Landmarks
    # --------------------------------------------------------

    for nome in selected_landmarks:

        coordinates = get_landmark_coordinates(
            individual_data,
            nome,
        )

        if coordinates is None:

            problems.append(
                "missing landmark: " + nome
            )


    # --------------------------------------------------------
    # Semilandmarks
    # --------------------------------------------------------

    for group_name in selected_semilandmarks:

        coordinates = get_semilandmark_coordinates(
            individual_data,
            group_name,
        )

        if coordinates is None:

            problems.append(
                "semimissing landmark: "
                + group_name
            )

        elif len(coordinates) == 0:

            problems.append(
                "empty semilandmark group: "
                + group_name
            )


    return problems


def check_semilandmark_counts(
    project,
    selected_individuals,
    selected_semilandmarks,
):
    """
    Controlla che ogni curva selezionata abbia lo stesso
    number di coordinates in tutti gli individui.
    """

    problems = []

    for group_name in selected_semilandmarks:

        counts = {}

        for code in selected_individuals:

            individual_data = (
                project["individuals"][code]
            )

            coordinates = get_semilandmark_coordinates(
                individual_data,
                group_name,
            )

            if coordinates is None:
                continue

            counts[code] = len(coordinates)


        values = list(counts.values())

        if len(values) == 0:
            continue


        expected_number = values[0]

        for code, number in counts.items():

            if number != expected_number:

                problems.append(
                    group_name
                    + ": "
                    + code
                    + " has "
                    + str(number)
                    + " coordinates; expected "
                    + str(expected_number)
                )

    return problems


def check_total_point_counts(
    project,
    selected_individuals,
    selected_landmarks,
    selected_semilandmarks,
):
    """
    Controlla che tutti gli individui selezionati abbiano
    lo stesso number totale di points.
    """

    counts = {}

    for code in selected_individuals:

        individual_data = (
            project["individuals"][code]
        )

        points = get_individual_points(
            individual_data,
            selected_landmarks,
            selected_semilandmarks,
        )

        counts[code] = len(points)


    values = list(counts.values())

    if len(values) == 0:

        return True, counts


    expected_number = values[0]

    for number in values:

        if number != expected_number:

            return False, counts


    return True, counts


# ============================================================
# 6. TPS EXPORT
# ============================================================

def export_tps(
    project,
    selected_individuals,
    selected_landmarks,
    selected_semilandmarks,
    output_path,
):
    """
    Export gli individui selezionati nel formato TPS.
    """

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        for progressive_id, code in enumerate(
            selected_individuals,
            start=1,
        ):

            individual_data = (
                project["individuals"][code]
            )

            points = get_individual_points(
                individual_data,
                selected_landmarks,
                selected_semilandmarks,
            )


            file.write(
                "LM="
                + str(len(points))
                + "\n"
            )


            for point_name, x, y in points:

                file.write(
                    str(x)
                    + " "
                    + str(y)
                    + "\n"
                )


            # Write the specimen/file name before the progressive ID.
            # The individual code is used as the file name because it identifies
            # the specimen in the project JSON.
            file.write(
                "IMAGE="
                + str(code)
                + "\n"
            )

            file.write(
                "ID="
                + str(progressive_id)
                + "\n"
            )


            file.write("\n")


# ============================================================
# 7. TXT EXPORT
# ============================================================

def export_txt(
    project,
    selected_individuals,
    selected_landmarks,
    selected_semilandmarks,
    output_path,
):
    """
    Export in formato lungo:

        individuo    punto    x    y
    """

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            "individual\tpoint\tx\ty\n"
        )


        for code in selected_individuals:

            individual_data = (
                project["individuals"][code]
            )

            points = get_individual_points(
                individual_data,
                selected_landmarks,
                selected_semilandmarks,
            )


            for point_name, x, y in points:

                file.write(
                    code
                    + "\t"
                    + point_name
                    + "\t"
                    + str(x)
                    + "\t"
                    + str(y)
                    + "\n"
                )


# ============================================================
# 8. CHECKBOX LIST
# ============================================================

class ListaCheckbox(QGroupBox):
    """
    Scrollable checkbox group with All and None buttons.
    """

    def __init__(
        self,
        titolo,
        names,
        parent=None,
    ):

        super().__init__(
            titolo,
            parent,
        )

        self.checkbox = {}

        main_layout = QVBoxLayout(self)


        # ----------------------------------------------------
        # Buttons
        # ----------------------------------------------------

        button_layout = QHBoxLayout()

        select_all_button = QPushButton("All")
        select_none_button = QPushButton("None")

        select_all_button.clicked.connect(
            self.select_all
        )

        select_none_button.clicked.connect(
            self.select_none
        )

        button_layout.addWidget(
            select_all_button
        )

        button_layout.addWidget(
            select_none_button
        )

        main_layout.addLayout(
            button_layout
        )


        # ----------------------------------------------------
        # Scrollable area
        # ----------------------------------------------------

        scroll_area = QScrollArea()

        scroll_area.setWidgetResizable(True)

        container = QWidget()

        list_layout = QGridLayout(
            container
        )

        number_of_columns = 3

        for index, nome in enumerate(names):

            checkbox = QCheckBox(nome)

            checkbox.setChecked(True)

            self.checkbox[nome] = checkbox

            row = index // number_of_columns
            column = index % number_of_columns

            list_layout.addWidget(
                checkbox,
                row,
                column
            )

        scroll_area.setWidget(
            container
        )

        main_layout.addWidget(
            scroll_area
        )


    def select_all(self):

        for checkbox in self.checkbox.values():

            checkbox.setChecked(True)


    def select_none(self):

        for checkbox in self.checkbox.values():

            checkbox.setChecked(False)


    def get_selected(self):

        selezionati = []

        for nome, checkbox in self.checkbox.items():

            if checkbox.isChecked():

                selezionati.append(nome)

        return selezionati


# ============================================================
# 9. EXPORT DIALOG
# ============================================================

class ExportDialog(QDialog):
    """
    Window per selezionare:

        - individui
        - landmark
        - curve di semilandmark
        - formato TPS o TXT
    """

    def __init__(
        self,
        json_path,
        parent=None,
    ):

        super().__init__(parent)

        self.json_path = Path(
            json_path
        )


        # ----------------------------------------------------
        # Legge il project
        # ----------------------------------------------------

        self.project = read_project(
            self.json_path
        )


        # ----------------------------------------------------
        # Available elements
        # ----------------------------------------------------

        self.individui = get_individuals(
            self.project
        )

        self.landmarks = get_landmarks(
            self.project
        )

        self.semilandmarks = get_semilandmarks(
            self.project
        )


        # ----------------------------------------------------
        # Window
        # ----------------------------------------------------

        self.setWindowTitle(
            "Export results"
        )

        self.resize(
            950,
            650
        )

        self.create_interface()


    def create_interface(self):

        main_layout = QVBoxLayout(self)


        # ====================================================
        # Informazioni sul project
        # ====================================================

        project_data = self.project.get(
            "project",
            {}
        )

        project_name = project_data.get(
            "name",
            self.json_path.stem
        )


        project_label = QLabel(
            "Project: "
            + str(project_name)
        )

        main_layout.addWidget(
            project_label
        )


        count_label = QLabel(
            "Individuals in project: "
            + str(len(self.individui))
        )

        main_layout.addWidget(
            count_label
        )


        # ====================================================
        # Central area
        # ====================================================

        upper_layout = QHBoxLayout()


        # ----------------------------------------------------
        # Individuals
        # ----------------------------------------------------

        self.individual_list = ListaCheckbox(
            "Individuals",
            self.individui,
        )

        upper_layout.addWidget(
            self.individual_list
        )


        # ----------------------------------------------------
        # Landmarkss and semilandmarks
        # ----------------------------------------------------

        point_layout = QVBoxLayout()

        self.landmark_list = ListaCheckbox(
            "Landmarkss",
            self.landmarks,
        )

        self.semilandmark_list = ListaCheckbox(
            "Semilandmarkss",
            self.semilandmarks,
        )


        point_layout.addWidget(
            self.landmark_list
        )

        point_layout.addWidget(
            self.semilandmark_list
        )


        upper_layout.addLayout(
            point_layout
        )

        main_layout.addLayout(
            upper_layout
        )


        # ====================================================
        # Format
        # ====================================================

        format_group = QGroupBox(
            "Format"
        )

        format_layout = QHBoxLayout(
            format_group
        )


        self.radio_tps = QRadioButton(
            "TPS"
        )

        self.radio_txt = QRadioButton(
            "TXT"
        )


        self.radio_tps.setChecked(True)


        format_layout.addWidget(
            self.radio_tps
        )

        format_layout.addWidget(
            self.radio_txt
        )

        format_layout.addStretch()


        main_layout.addWidget(
            format_group
        )


        # ====================================================
        # Note
        # ====================================================

        note = QLabel(
        "The coordinates are read directly "
        "from the 'individuals' section of the project."
        )

        note.setWordWrap(True)

        main_layout.addWidget(
            note
        )


        # ====================================================
        # Buttons
        # ====================================================

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
        )


        buttons.button(
            QDialogButtonBox.Ok
        ).setText(
            "Export"
        )


        buttons.button(
            QDialogButtonBox.Cancel
        ).setText(
            "Cancel"
        )


        buttons.accepted.connect(
            self.export
        )

        buttons.rejected.connect(
            self.reject
        )


        main_layout.addWidget(
            buttons
        )


    # ========================================================
    # ESPORTAZIONE
    # ========================================================

    def export(self):

        selected_individuals = (
            self.individual_list.get_selected()
        )

        selected_landmarks = (
            self.landmark_list.get_selected()
        )

        selected_semilandmarks = (
            self.semilandmark_list.get_selected()
        )


        # ----------------------------------------------------
        # Basic checks
        # ----------------------------------------------------

        if len(selected_individuals) == 0:

            QMessageBox.warning(
                self,
                "Exported",
                "No individual has been selected.",
            )

            return


        if (
            len(selected_landmarks) == 0
            and len(selected_semilandmarks) == 0
        ):

            QMessageBox.warning(
                self,
                "Exported",
                "No point has been selected.",
            )

            return


        # ====================================================
        # Missing data
        # ====================================================

        problems = []

        for code in selected_individuals:

            individual_data = (
                self.project["individuals"][code]
            )

            errors = check_individual(
                individual_data,
                selected_landmarks,
                selected_semilandmarks,
            )

            for error in errors:

                problems.append(
                    code
                    + ": "
                    + error
                )


        if len(problems) > 0:

            text = (
            "Export is not possible because "
            "some individuals have missing data:\n\n"
                + "\n".join(problems)
            )

            QMessageBox.warning(
                self,
                "Incomplete data",
                text,
            )

            return


        # ====================================================
        # Number of semilandmarks
        # ====================================================

        curve_problems = check_semilandmark_counts(
            self.project,
            selected_individuals,
            selected_semilandmarks,
        )


        if len(curve_problems) > 0:

            text = (
                "The selected curves do not have the"
                "same number of di coordinates in all speciemens "
                ":\n\n"
                + "\n".join(curve_problems)
            )

            QMessageBox.warning(
                self,
                "Different number of semilandmarks",
                text,
            )

            return


        # ====================================================
        # Numero totale di points
        # ====================================================

        same, counts = check_total_point_counts(
            self.project,
            selected_individuals,
            selected_landmarks,
            selected_semilandmarks,
        )


        if not same:

            rows = []

            for code, number in counts.items():

                rows.append(
                    code
                    + ": "
                    + str(number)
                    + " points"
                )


            text = (
                "Speciemens do not have the same "
                "total number of points:\n\n"
                + "\n".join(rows)
            )


            QMessageBox.warning(
                self,
                "Different number of points ",
                text,
            )

            return


        # ====================================================
        # Export TPS
        # ====================================================

        if self.radio_tps.isChecked():

            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save TPS file",
                "",
                "TPS files (*.tps)",
            )


            if not output_path:
                return


            if not output_path.lower().endswith(
                ".tps"
            ):

                output_path += ".tps"


            export_tps(
                self.project,
                selected_individuals,
                selected_landmarks,
                selected_semilandmarks,
                output_path,
            )


        # ====================================================
        # Export TXT
        # ====================================================

        else:

            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save TXT file",
                "",
                "Text files (*.txt)",
            )


            if not output_path:
                return


            if not output_path.lower().endswith(
                ".txt"
            ):

                output_path += ".txt"


            export_txt(
                self.project,
                selected_individuals,
                selected_landmarks,
                selected_semilandmarks,
                output_path,
            )


        # ====================================================
        # Finish
        # ====================================================

        QMessageBox.information(
            self,
            "Export",
            "Export completed.",
        )

        self.accept()


# ============================================================
# 10. TEST WINDOW
# ============================================================

class MainWindow(QWidget):
    """
    Window usata soltanto per provare il modulo.

    Nell'integrazione definitiva in SMORPHILA
    potrà essere eliminata.
    """

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "SMORPHILA - Export project"
        )

        self.resize(
            500,
            200
        )


        layout = QVBoxLayout(self)


        text = QLabel(
            "Select a SMORPHILA project file "
            "with more than one individual."
        )

        text.setWordWrap(True)

        layout.addWidget(
            text
        )


        button = QPushButton(
            "Open project and export"
        )


        button.clicked.connect(
            self.open_project
        )


        layout.addWidget(
            button
        )

        layout.addStretch()


    def open_project(self):

        json_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open project SMORPHILA",
            "",
            "JSON files (*.json)",
        )


        if not json_path:
            return


        try:

            project = read_project(
                json_path
            )


        except Exception as error:

            QMessageBox.critical(
                self,
                "Error",
                "the project can't be opened:\n\n"
                + str(error),
            )

            return


        if len(project.get("individuals", {})) == 0:

            QMessageBox.warning(
                self,
                "SMORPHILA",
                "the project is empty.",
            )

            return


        dialog = ExportDialog(
            json_path,
            self,
        )

        dialog.exec()


# ============================================================
# 11. START APPLICATION
# ============================================================

def run():

    app = QApplication(sys.argv)

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":

    run()
