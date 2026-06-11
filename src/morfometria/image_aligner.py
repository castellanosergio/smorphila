from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QTransform, QColor, Qt
from PySide6.QtCore import QRect
import math


class ImageAligner:
    def __init__(self, viewer):
        self.viewer = viewer
        self.points = []
        self.active = False

    def align_image(self):
        self.viewer.mode_label.setText("ALIGNMENT MODE")

        self.points = []
        self.active = True
        self.viewer.disattiva_zoom()
        self.viewer.image.setCursor(Qt.CrossCursor)

        QMessageBox.information(
            self.viewer,
            "Axis definition",
            "Click the point to use as the origin (0,0), then click a second point to define the Y-axis direction.",
        )

    def handle_click(self, pos):
        if not self.active:
            return

        self.points.append(pos)

        self.viewer.layer_manager.draw_points(
            "axis_definition", self.points, color=QColor(0, 100, 255, 150)
        )

        if len(self.points) == 2:
            self.active = False
            self.viewer.image.setCursor(Qt.OpenHandCursor)
            self.finalize_transformation()

    def finalize_transformation(self):
        p1, p2 = self.points
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()

        if dx == 0 and dy == 0:
            QMessageBox.warning(
                self.viewer, "Error", "The two points must be distinct."
            )
            return

        # Allineamento con asse Y verso l'alto
        angle_rad = math.atan2(-dx, -dy)
        angle_deg = math.degrees(angle_rad)
        if self.viewer.angle_deg:
            self.viewer.angle_deg += angle_deg
        else:
            self.viewer.angle_deg = angle_deg
        transform = QTransform()
        transform.translate(-p1.x(), -p1.y())
        transform.rotate(angle_deg)

        transformed_pixmap = self.viewer.pixmap.transformed(
            transform, Qt.SmoothTransformation
        )

        axis_definition = self.viewer.layer_manager.layers[
            "axis_definition"
        ].transformed(transform, Qt.SmoothTransformation)
        self.viewer.layer_manager.layers["axis_definition"] = axis_definition
        self.viewer.layer_manager.visible["axis_definition"] = True

        self.viewer.pixmap = transformed_pixmap
        self.viewer.image.setPixmap(transformed_pixmap)
        self.viewer.scaled_pixmap = transformed_pixmap

        # Intersezione con i limiti dell'immagine originale

        full_rect = QRect(0, 0, self.viewer.pixmap.width(), self.viewer.pixmap.height())
        self.viewer.set_view_rect(full_rect)

        # corrected_rect = transformed_pixmap.intersected(full_rect)
        # self.set_view_rect(corrected_rect)
        self.viewer.layer_manager.update_display()

        """
        QMessageBox.information(
            self.viewer,
            "Transformation complete",
            "The image has been centered on the origin and rotated.",
        )
        """

        self.viewer.status_bar.showMessage(
            "Transformation complete: the image has been centered on the origin and rotated."
        )

        self.viewer.layer_manager.clear_layer("axis_definition")

        self.viewer.mode_label.setText("")
