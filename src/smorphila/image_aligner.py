from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QPixmap, QTransform, QColor, Qt
from PySide6.QtCore import QPointF, QRect
import math


class ImageAligner:
    def __init__(self, viewer):
        self.viewer = viewer
        self.points = []
        self.active = False
        self.reference_landmarks = None

    def align_image(self):
        self.reference_landmarks = None
        self._start_alignment(
            "Click the point to use as the origin (0,0), then click a second point to define the Y-axis direction."
        )

    def align_reference_axis(self, landmark_names):
        """Align a new image using the two project reference-axis landmarks."""

        self.reference_landmarks = landmark_names
        self._start_alignment(
            f"Click reference landmark '{landmark_names[0]}', then '{landmark_names[1]}'."
        )

    def align_project_reference_axis(self, landmark_names):
        """Align an image from already placed reference-axis landmarks."""

        self.reference_landmarks = landmark_names
        self.points = [
            QPointF(*self.viewer.landmarks[name]["coordinates"])
            for name in landmark_names
        ]
        self.finalize_transformation()

    def _start_alignment(self, instruction):
        self.viewer.mode_label.setText("ALIGNMENT MODE")

        self.points = []
        self.active = True
        self.viewer.disattiva_zoom()
        self.viewer.image.setCursor(Qt.CrossCursor)

        QMessageBox.information(
            self.viewer,
            "Axis definition",
            instruction,
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
        display_transform = QPixmap.trueMatrix(
            transform, self.viewer.pixmap.width(), self.viewer.pixmap.height()
        )

        if self.reference_landmarks is not None:
            analytical_origin = transform.map(p1)
            display_origin = display_transform.map(p1)
            self.viewer.coordinate_display_offset = (
                display_origin.x(),
                display_origin.y(),
            )
            self.viewer.raw_to_display_transform = {
                "m11": display_transform.m11(), "m12": display_transform.m12(),
                "m21": display_transform.m21(), "m22": display_transform.m22(),
                "dx": display_transform.dx(), "dy": display_transform.dy(),
            }
            for landmark in self.viewer.landmarks.values():
                coordinates = landmark.get("coordinates")
                if not coordinates:
                    continue
                mapped = transform.map(QPointF(*coordinates))
                landmark["coordinates"] = (
                    mapped.x() - analytical_origin.x(),
                    mapped.y() - analytical_origin.y(),
                )

        transformed_pixmap = self.viewer.pixmap.transformed(
            transform, Qt.SmoothTransformation
        )

        if "axis_definition" in self.viewer.layer_manager.layers:
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
        self.reference_landmarks = None
