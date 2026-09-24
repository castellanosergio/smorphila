import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox


class SpezzataAligner:
    def __init__(self, viewer):
        self.viewer = viewer
        self.points = []
        self.active = False
        self.show_all_points = True

    def start(self):
        self.points = []
        self.active = True
        self.viewer.disattiva_zoom()
        self.viewer.image.setCursor(Qt.CrossCursor)
        self.viewer.selection_mode = False
        if self.viewer.insert_landmarks.active:
            self.viewer.insert_landmarks.deactivate()

    def handle_click(self, pos: QPointF):
        self.points.append(pos)
        self.draw_preview()

    def handle_double_click(self):
        if len(self.points) < 2:
            QMessageBox.warning(self.viewer, "Error", "Enter at least two points.")
            return
        aligned = self.straighten_polyline(self.points)

        scelta = QMessageBox.question(
            self.viewer,
            "Show points",
            "Do you want to display all points in the polyline?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        self.show_all_points = scelta == QMessageBox.Yes

        if not self.show_all_points and len(aligned) > 2:
            aligned = [aligned[0], aligned[-1]]

        self.points = aligned
        self.active = False
        self.viewer.image.setCursor(Qt.OpenHandCursor)
        self.draw_on_layer()

    def straighten_polyline(self, points):
        if len(points) < 2:
            return points[:]

        # Fit the OLS regression line: y = intercept + slope * x.
        mean_x = sum(point.x() for point in points) / len(points)
        mean_y = sum(point.y() for point in points) / len(points)
        denominator = sum((point.x() - mean_x) ** 2 for point in points)

        if denominator == 0:
            # A vertical line cannot be represented by y = intercept + slope * x.
            direction_angle = math.pi / 2
        else:
            slope = sum(
                (point.x() - mean_x) * (point.y() - mean_y)
                for point in points
            ) / denominator
            direction_angle = math.atan2(slope, 1)

        # Keep the direction consistent with the clicked point sequence.
        direction_x = math.cos(direction_angle)
        direction_y = math.sin(direction_angle)
        sequence_x = points[-1].x() - points[0].x()
        sequence_y = points[-1].y() - points[0].y()

        if direction_x * sequence_x + direction_y * sequence_y < 0:
            direction_angle += math.pi

        distances = [
            math.hypot(
                points[i + 1].x() - points[i].x(), points[i + 1].y() - points[i].y()
            )
            for i in range(len(points) - 1)
        ]

        direction_x = math.cos(direction_angle)
        direction_y = math.sin(direction_angle)

        aligned_points = [points[0]]
        current_pos = points[0]

        for distance in distances:
            next_point = QPointF(
                current_pos.x() + distance * direction_x,
                current_pos.y() + distance * direction_y,
            )
            aligned_points.append(next_point)
            current_pos = next_point

        return aligned_points

    def draw_preview(self):
        """Show the clicked points on the layer in real time."""
        self.viewer.layer_manager.clear_layer("spezzata")
        self.viewer.layer_manager.draw_points(
            "spezzata", self.points, color=QColor(255, 255, 255, 150)
        )

    def draw_on_layer(self):
        """Draw the final polyline on a layer."""
        if len(self.points) < 2:
            return
        self.viewer.layer_manager.clear_layer("spezzata")
        self.viewer.layer_manager.draw_points("spezzata", self.points, color=Qt.green)
