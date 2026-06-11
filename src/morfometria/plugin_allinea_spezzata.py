from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QColor
import math


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
        if self.viewer.inserisci_landmarks.active:
            self.viewer.inserisci_landmarks.deactivate()

    def handle_click(self, pos: QPointF):
        self.points.append(pos)
        self.draw_preview()

    def handle_double_click(self):
        if len(self.points) < 2:
            QMessageBox.warning(self.viewer, "Error", "Enter at least two points.")
            return
        aligned = self.straighten_polyline(self.points)

        # Ask whether to show all points or only the first/last
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

        self.points = aligned  # keep only the aligned ones
        self.active = False
        self.viewer.image.setCursor(Qt.OpenHandCursor)

        # Draw on the layer
        self.draw_on_layer()

    def straighten_polyline(self, points):
        if len(points) < 2:
            return points[:]

        dx = self.points[1].x() - self.points[0].x()
        dy = self.points[1].y() - self.points[0].y()
        angolo_con_asse = math.atan2(dy, dx)
        direction_angle = self.determina_direzione_allineamento(angolo_con_asse)

        distances = [math.hypot(points[i + 1].x() - points[i].x(), points[i + 1].y() - points[i].y()) for i in range(len(points) - 1)]

        dx = math.cos(direction_angle)
        dy = math.sin(direction_angle)

        aligned_points = [points[0]]
        current_pos = points[0]

        for d in distances:
            next_point = QPointF(current_pos.x() + d * dx, current_pos.y() + d * dy)
            aligned_points.append(next_point)
            current_pos = next_point

        return aligned_points

    def draw_preview(self):
        """Show the clicked points on the layer in real time."""
        self.viewer.layer_manager.clear_layer("spezzata")
        self.viewer.layer_manager.draw_points("spezzata", self.points, color=QColor(255, 255, 255, 150))

    def draw_on_layer(self):
        """Draw the final polyline on a layer."""
        if len(self.points) < 2:
            return
        self.viewer.layer_manager.clear_layer("spezzata")
        self.viewer.layer_manager.draw_points("spezzata", self.points, color=Qt.green)

    def determina_direzione_allineamento(self, angolo_rad):
        # Convert the angle to degrees
        angolo_gradi = math.degrees(angolo_rad)

        # Normalize the angle to the [0, 360) range
        angolo_normalizzato = angolo_gradi % 360

        # Determine the direction according to the defined thresholds
        if -45 <= angolo_gradi < 45 or angolo_normalizzato < 45 or angolo_normalizzato >= 315:
            return 0  # Horizontal (east)
        elif 45 <= angolo_normalizzato < 135:
            return math.pi / 2  # Vertical (north)
        elif 135 <= angolo_normalizzato < 225:
            return math.pi  # Opposite horizontal (west)
        elif 225 <= angolo_normalizzato < 315:
            return -math.pi / 2  # Opposite vertical (south)
