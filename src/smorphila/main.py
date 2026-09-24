"""Launcher and status window for a unified SMORPHILA project."""

from __future__ import annotations

import pathlib as pl
import subprocess
import sys

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from .project_store import (
        create_project,
        inconsistent_individuals,
        load_project,
        save_project,
    )
except ImportError:
    from project_store import (
        create_project,
        inconsistent_individuals,
        load_project,
        save_project,
    )


class ProjectHub(QMainWindow):
    """Manage one project and launch its three workflow stages."""

    def __init__(self, project_path: pl.Path | None = None):
        super().__init__()
        self.project_path: pl.Path | None = None
        self.inconsistent_records: dict[str, list[str]] = {}
        self.setWindowTitle("SMORPHILA")
        self.resize(480, 320)
        self._build_interface()
        if project_path is not None:
            self._open_project_path(project_path)

    def _build_interface(self):
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)

        project_buttons = QHBoxLayout()
        new_button = QPushButton("New project")
        open_button = QPushButton("Open project")
        refresh_button = QPushButton("Refresh")
        new_button.clicked.connect(self._new_project)
        open_button.clicked.connect(self._open_project)
        refresh_button.clicked.connect(self._refresh_project)
        project_buttons.addWidget(new_button)
        project_buttons.addWidget(open_button)
        project_buttons.addWidget(refresh_button)
        layout.addLayout(project_buttons)

        summary = QFormLayout()
        self.project_name_label = QLabel("No project open")
        self.project_path_label = QLabel("")
        self.definition_label = QLabel("")
        self.individual_label = QLabel("")
        self.record_status_label = QLabel("")
        self.project_path_label.setWordWrap(True)
        summary.addRow("Project:", self.project_name_label)
        summary.addRow("File:", self.project_path_label)
        summary.addRow("Definitions:", self.definition_label)
        summary.addRow("Individuals:", self.individual_label)
        summary.addRow("Record status:", self.record_status_label)
        layout.addLayout(summary)

        self.define_button = QPushButton("Define project")
        self.acquire_button = QPushButton("Acquire data")
        self.export_button = QPushButton("Export data")
        self.review_records_button = QPushButton("Review inconsistent records")
        self.define_button.clicked.connect(lambda: self._launch_tool("landmark_editor"))
        self.acquire_button.clicked.connect(
            lambda: self._launch_tool("data_acquisition")
        )
        self.export_button.clicked.connect(
            lambda: self._launch_tool("smorphila_export_project")
        )
        self.review_records_button.clicked.connect(self._review_inconsistent_records)
        layout.addWidget(self.define_button)
        layout.addWidget(self.acquire_button)
        layout.addWidget(self.export_button)
        layout.addWidget(self.review_records_button)
        layout.addStretch()

        self.setCentralWidget(central_widget)
        self._update_summary(None)

    def _new_project(self):
        name, accepted = QInputDialog.getText(self, "New project", "Project name:")
        if not accepted or not name.strip():
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save project", "", "JSON files (*.json)"
        )
        if not file_name:
            return
        path = pl.Path(file_name).with_suffix(".json")
        try:
            (path.parent / "images").mkdir(exist_ok=True)
            save_project(path, create_project(name.strip()))
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "New project", str(error))
            return
        self._open_project_path(path)

    def _open_project(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open project", "", "JSON files (*.json)"
        )
        if file_name:
            self._open_project_path(pl.Path(file_name))

    def _open_project_path(self, path: pl.Path):
        try:
            project = load_project(path)
        except ValueError as error:
            QMessageBox.critical(self, "Open project", str(error))
            return
        self.project_path = path
        self._update_summary(project)

    def _refresh_project(self):
        if self.project_path is not None:
            self._open_project_path(self.project_path)

    def _update_summary(self, project: dict | None):
        is_open = project is not None
        self.define_button.setEnabled(is_open)
        self.acquire_button.setEnabled(
            is_open and bool(project["definitions"].get("landmarks", {}))
        )
        self.export_button.setEnabled(is_open and bool(project["individuals"]))
        if not is_open:
            self.project_name_label.setText("No project open")
            self.project_path_label.clear()
            self.definition_label.clear()
            self.individual_label.clear()
            self.record_status_label.clear()
            self.inconsistent_records = {}
            self.review_records_button.setEnabled(False)
            return
        definitions = project["definitions"]
        self.project_name_label.setText(str(project["project"].get("name", "Untitled")))
        self.project_path_label.setText(str(self.project_path))
        self.definition_label.setText(
            f"{len(definitions.get('landmarks', {}))} landmarks, "
            f"{len(definitions.get('distances', {}))} distances"
        )
        self.individual_label.setText(str(len(project["individuals"])))
        self.inconsistent_records = inconsistent_individuals(project)
        incompatible_count = len(self.inconsistent_records)
        compatible_count = len(project["individuals"]) - incompatible_count
        self.record_status_label.setText(
            f"{compatible_count} compatible, {incompatible_count} need review"
        )
        self.review_records_button.setEnabled(bool(self.inconsistent_records))

    def _review_inconsistent_records(self):
        if not self.inconsistent_records:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Inconsistent records")
        dialog.resize(520, 320)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel("The following records do not match the current project definition:")
        )
        record_list = QListWidget()
        for code, reasons in self.inconsistent_records.items():
            record_list.addItem(f"{code}\n  - " + "\n  - ".join(reasons))
        layout.addWidget(record_list)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _launch_tool(self, module: str):
        if self.project_path is None:
            return
        package_root = pl.Path(__file__).resolve().parent.parent
        try:
            subprocess.Popen(
                [sys.executable, "-m", f"smorphila.{module}", str(self.project_path)],
                cwd=package_root,
            )
        except OSError as error:
            QMessageBox.critical(self, "Launch tool", str(error))


def run():
    app = QApplication(sys.argv)
    project_path = pl.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    hub = ProjectHub(project_path)
    hub.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
