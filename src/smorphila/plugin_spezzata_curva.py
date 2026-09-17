from math import atan2, cos, degrees, hypot, pi, sin

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)


class CurveSelectionDialog(QDialog):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.setWindowTitle("Select curve")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose a configured curve:"))
        self.curve_combo = QComboBox()
        self.curve_combo.addItems(viewer.curves)
        layout.addWidget(self.curve_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_curve_name(self):
        return self.curve_combo.currentText()


class SpezzataCurva:
    def __init__(self, viewer):
        self.viewer = viewer
        self.color_points = QColor(0, 255, 0, 255)
        self.points = []
        self.qpoints = []
        self.active = False
        self.show_all_points = True
        self.curve_name = None

    def start(self):
        if not self.viewer.curves:
            QMessageBox.warning(
                self.viewer,
                "Semilandmarks",
                "Load a project that defines at least one curve first.",
            )
            return

        dialog = CurveSelectionDialog(self.viewer)
        if not dialog.exec():
            return

        curve_name = dialog.selected_curve_name()
        curve = self.viewer.curves[curve_name]
        start_name = curve["start_landmark"]
        end_name = curve["end_landmark"]
        start_coordinates = self.viewer.landmarks[start_name]["coordinates"]
        end_coordinates = self.viewer.landmarks[end_name]["coordinates"]
        if not start_coordinates or not end_coordinates:
            QMessageBox.warning(
                self.viewer,
                "Semilandmarks",
                "Place both curve anchor landmarks before tracing the curve.",
            )
            return

        self.curve_name = curve_name
        self.viewer.mode_label.setText(f"SEMI LANDMARKS MODE: {curve_name}")
        self.points = []
        self.qpoints = []
        self.active = True
        self.viewer.disattiva_zoom()
        self.viewer.selection_mode = False
        if self.viewer.insert_landmarks.active:
            self.viewer.insert_landmarks.deactivate()
        self.viewer.layer_manager.clear_layer("preview")
        QMessageBox.information(
            self.viewer,
            "Point entry",
            f"Trace '{curve_name}' and double-click to finish.",
        )

    def handle_click(self, pos: QPointF):
        self.viewer.image.setCursor(Qt.CrossCursor)
        offset_x, offset_y = self.viewer.coordinate_display_offset
        analytical_pos = QPointF(pos.x() - offset_x, pos.y() - offset_y)
        self.points.append((analytical_pos.x(), analytical_pos.y()))
        self.qpoints.append(analytical_pos)
        self.draw_preview()

    def handle_double_click(self):
        if len(self.points) < 2:
            QMessageBox.warning(self.viewer, "Error", "Enter at least two points.")
            return

        if self.curve_name is None:
            return

        curve = self.viewer.curves[self.curve_name]
        start_name = curve["start_landmark"]
        end_name = curve["end_landmark"]
        start_anchor = tuple(self.viewer.landmarks[start_name]["coordinates"])
        end_anchor = tuple(self.viewer.landmarks[end_name]["coordinates"])
        start_index = self.trova_punto_piu_vicino(start_anchor, self.points)
        end_index = self.trova_punto_piu_vicino(end_anchor, self.points)
        if start_index <= end_index:
            traced_points = self.points[start_index : end_index + 1]
        else:
            traced_points = list(reversed(self.points[end_index : start_index + 1]))
        polyline = [start_anchor]
        for point in traced_points:
            if point != polyline[-1]:
                polyline.append(point)
        if end_anchor != polyline[-1]:
            polyline.append(end_anchor)
        try:
            coordinates = self.interpolate_line_fixed_number(
                polyline, curve["point_count"]
            )
        except ValueError as error:
            QMessageBox.warning(self.viewer, "Semilandmarks", str(error))
            return
        self.viewer.semilandmarks[self.curve_name]["coordinates"] = coordinates

        curve_layer = f"curve:{self.curve_name}"
        self.viewer.layer_manager.clear_layer(curve_layer)
        self.viewer.layer_manager.draw_lines(
            curve_layer, coordinates, color=self.color_points
        )
        self.viewer.layer_manager.create_layer("semilandmarks")
        self.viewer.layer_manager.clear_layer("preview")
        self.viewer.layer_manager.update_display()
        self.active = False
        self.curve_name = None

        self.viewer.mode_label.setText("")

    def draw_preview(self):
        """Mostra in tempo reale i punti cliccati su layer"""
        self.viewer.layer_manager.clear_layer("preview")
        self.viewer.layer_manager.draw_points(
            "preview", self.qpoints, color=QColor(0, 255, 0, 255)
        )

    def trova_punto_piu_vicino(self, punto, contorno):
        A = np.array(contorno)
        B = np.ones_like(A) * punto
        diff = A - B
        dist_sq = np.sum(diff**2, axis=1)
        indice = np.argmin(dist_sq)
        return indice

    def interpolate_line_fixed_number(self, points, n):
        """Return n + 1 equally spaced points along a polyline."""

        segments = []
        total_length = 0.0
        for start, end in zip(points[:-1], points[1:]):
            length = hypot(end[0] - start[0], end[1] - start[1])
            if length == 0:
                continue
            segments.append((start, end, length))
            total_length += length
        if total_length == 0:
            raise ValueError("The traced curve must have a non-zero length.")

        sampled_points = []
        segment_index = 0
        length_before_segment = 0.0
        for point_index in range(n + 1):
            target_length = total_length * point_index / n
            while (
                segment_index < len(segments) - 1
                and target_length > length_before_segment + segments[segment_index][2]
            ):
                length_before_segment += segments[segment_index][2]
                segment_index += 1
            start, end, length = segments[segment_index]
            ratio = (target_length - length_before_segment) / length
            sampled_points.append(
                (
                    start[0] + ratio * (end[0] - start[0]),
                    start[1] + ratio * (end[1] - start[1]),
                )
            )
        return sampled_points

    def straighten_polyline(self, points):
        if len(points) < 2:
            return points[:]

        dx = points[1].x() - points[0].x()
        dy = points[1].y() - points[0].y()
        angolo_con_asse = atan2(dy, dx)
        direction_angle = self.determina_direzione_allineamento(angolo_con_asse)

        distances = [
            hypot(points[i + 1].x() - points[i].x(), points[i + 1].y() - points[i].y())
            for i in range(len(points) - 1)
        ]

        dx = cos(direction_angle)
        dy = sin(direction_angle)

        aligned_points = [points[0]]
        current_pos = points[0]

        for d in distances:
            next_point = QPointF(current_pos.x() + d * dx, current_pos.y() + d * dy)
            aligned_points.append(next_point)
            current_pos = next_point

        return aligned_points

    def determina_direzione_allineamento(self, angolo_rad):
        # Converti l'angolo in gradi
        angolo_gradi = degrees(angolo_rad)

        # Porta l'angolo nel range [0, 360)
        angolo_normalizzato = angolo_gradi % 360

        # Determina la direzione secondo le soglie definite
        if (
            -45 <= angolo_gradi < 45
            or angolo_normalizzato < 45
            or angolo_normalizzato >= 315
        ):
            return 0  # Orizzontale (est)
        elif 45 <= angolo_normalizzato < 135:
            return pi / 2  # Verticale (nord)
        elif 135 <= angolo_normalizzato < 225:
            return pi  # Orizzontale opposta (ovest)
        elif 225 <= angolo_normalizzato < 315:
            return -pi / 2  # Verticale opposta (sud)
