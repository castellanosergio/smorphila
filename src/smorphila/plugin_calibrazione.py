# plugin_calibrazione.py

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QVBoxLayout,
    QPushButton,
    QComboBox,
    QMessageBox,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
import math

# scale = None  # Variabile globale


class ScaleDialog(QDialog):
    def __init__(self, pixel_length, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scale calibration")

        self.pixel_length = pixel_length

        self.pixel_display = QLineEdit(str(round(pixel_length, 2)))
        self.pixel_display.setReadOnly(True)

        self.real_spin = QDoubleSpinBox()
        self.real_spin.setRange(0.01, 100000)
        self.real_spin.setDecimals(4)
        self.real_spin.setValue(1.0)

        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["mm", "cm", "m", "µm"])

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Length in pixels:"))
        layout.addWidget(self.pixel_display)
        layout.addWidget(QLabel("Real length:"))
        layout.addWidget(self.real_spin)
        layout.addWidget(QLabel("Unit:"))
        layout.addWidget(self.unit_combo)
        layout.addWidget(apply_btn)

        self.setLayout(layout)

    def get_scale(self):
        real = self.real_spin.value()
        return real / self.pixel_length, self.unit_combo.currentText()


class CalibrationPlugin:
    def __init__(self, viewer):
        self.viewer = viewer
        self.active = False
        self.start_point = None
        self.end_point = None

    def activate(self):
        self.viewer.mode_label.setText("CALIBRATION MODE")

        self.active = True
        if "calibration" not in self.viewer.layer_manager.layers:
            self.viewer.layer_manager.create_layer("calibration")
        self.viewer.layer_manager.clear_layer("calibration")
        # Disattiva lo zoom
        self.viewer.disattiva_zoom()
        self.viewer.image.setCursor(Qt.CrossCursor)
        self.viewer.image.setFocus()
        QMessageBox.information(self.viewer, "Calibration", "Select two points at a known distance")
        self.count = 0
        self.cal_points = []
        self.viewer.image.setCursor(Qt.CrossCursor)
        print("STARTING CALIBRATION")

    def deactivate(self):
        self.active = False
        self.viewer.setCursor(Qt.ArrowCursor)
        self.viewer.image.setCursor(Qt.ArrowCursor)
        self.viewer.image.update()

        self.viewer.mode_label.setText("")

    def handle_click(self, pos):
        print("CALIBRATION IN PROGRESS")
        self.count += 1
        self.cal_points.append(pos)
        self.viewer.layer_manager.draw_points("calibration", self.cal_points, color=QColor(255, 0, 0, 180))
        if self.count == 2:
            self.calibrate(self.cal_points)
            self.cal_points = []
            self.viewer.layer_manager.clear_layer("calibration")
            self.deactivate()

    def calibrate(self, points):
        pixel_len = math.dist((points[0].x(), points[0].y()), (points[1].x(), points[1].y()))
        dialog = ScaleDialog(pixel_len, self.viewer)
        if dialog.exec():
            # global scale
            s, unit = dialog.get_scale()
            # scale = s
            self.viewer.scale = s
            self.viewer.scale_unit = unit

            self.viewer.scale_label.setText(f"Scale: {self.viewer.scale:.4f} {unit}/px")

            self.viewer.status_bar.showMessage(f"The scale has been set ({self.viewer.scale:.4f} {unit}/px)")
