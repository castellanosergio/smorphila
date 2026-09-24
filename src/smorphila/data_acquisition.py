"""
main program of smorphila package
"""

import copy
import json
import pathlib as pl
import sys
import tomllib

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCursor,
    QKeySequence,
    QPixmap,
    QShortcut,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QWidget,
)

from . import save_data
from .image_aligner import ImageAligner
from .insert_landmarks import LandmarkPlugin
from .layer_manager import LayerManager
from .layers_management.py import LayerPlugin
from .plugin_allinea_spezzata_ols import SpezzataAligner
from .plugin_arti import ArtiPlugin
from .plugin_calibrazione import CalibrationPlugin
from .plugin_spezzata_curva import SpezzataCurva
from .project_store import load_project
from .rileva_contorno import ContourPlugin

__version__ = "0.0.4"
__version_date__ = "2025-05-28"
IMAGE_EXTENSION = "*.jpg *.JPG *.png *.PNG"


class ClickableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewer = parent
        self.setFocusPolicy(Qt.StrongFocus)

    def enterEvent(self, event):
        if (
            self.viewer.insert_landmarks.active
            or self.viewer.spezzata_curva.active
            or self.viewer.calibrazione.active
        ):
            self.setCursor(Qt.CrossCursor)
            QApplication.setOverrideCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
            QApplication.setOverrideCursor(Qt.ArrowCursor)

    def leaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if self.viewer.calibrazione.active:
            mapped = self.map_to_pixmap_coordinates(event.position())
            self.viewer.calibrazione.handle_click(mapped)
            return

        if self.viewer.image_aligner.active:
            mapped = self.map_to_pixmap_coordinates(event.position())
            self.viewer.image_aligner.handle_click(mapped)
            return

        elif self.viewer.insert_landmarks.active:
            mapped = self.map_to_pixmap_coordinates(event.position())
            name = self.viewer.landmark_combo.currentText()

            self.viewer.insert_landmarks.handle_click(name, mapped)
            self.viewer.setCursor(Qt.CrossCursor)

        elif self.viewer.spezzata_plugin.active:
            if event.type() == QEvent.MouseButtonDblClick:
                self.viewer.spezzata_plugin.handle_double_click()
            else:
                mapped = self.map_to_pixmap_coordinates(event.position())
                self.viewer.spezzata_plugin.handle_click(mapped)
            return

        elif self.viewer.spezzata_curva.active:
            if event.type() == QEvent.MouseButtonDblClick:
                self.viewer.spezzata_curva.handle_double_click()
            else:
                mapped = self.map_to_pixmap_coordinates(event.position())
                self.viewer.spezzata_curva.handle_click(mapped)

        elif not self.viewer.selection_mode and event.button() == Qt.LeftButton:
            self.viewer.drag_start_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)

        elif self.viewer.selection_mode and event.button() == Qt.LeftButton:
            mapped_pos = self.map_to_pixmap_coordinates(event.position())
            self.viewer.start_point = mapped_pos
            self.viewer.end_point = mapped_pos
            self.viewer.selecting = True

    def mouseMoveEvent(self, event):
        if self.viewer.selection_mode and self.viewer.selecting:
            mapped_pos = self.map_to_pixmap_coordinates(event.position())
            self.viewer.end_point = mapped_pos

            # Draw the selection rectangle on the layer
            p1 = QPoint(
                int(self.viewer.start_point.x()), int(self.viewer.start_point.y())
            )
            p2 = QPoint(int(self.viewer.end_point.x()), int(self.viewer.end_point.y()))
            top_left = QPoint(min(p1.x(), p2.x()), min(p1.y(), p2.y()))
            bottom_right = QPoint(max(p1.x(), p2.x()), max(p1.y(), p2.y()))
            rect = QRect(top_left, bottom_right)
            self.viewer.layer_manager.clear_layer("zoom_preview")
            self.viewer.layer_manager.draw_rect("zoom_preview", rect)
            self.viewer.layer_manager.update_display()

        elif not self.viewer.selection_mode and event.buttons() == Qt.LeftButton:
            print(f"{self.viewer.selection_mode=}")

            if self.viewer.insert_landmarks.active or self.viewer.spezzata_curva.active:
                print("RETURN")
                return

            if (
                not hasattr(self.viewer, "view_rect")
                or self.viewer.drag_start_pos is None
            ):
                return

            dx = event.position().x() - self.viewer.drag_start_pos.x()
            dy = event.position().y() - self.viewer.drag_start_pos.y()

            # Scale according to the ratio between the image and the QLabel
            scale_x = self.viewer.pixmap.width() / self.size().width()
            scale_y = self.viewer.pixmap.height() / self.size().height()
            dx *= scale_x
            dy *= scale_y

            # Create the translated rectangle
            new_rect = QRect(self.viewer.view_rect)
            new_rect.translate(-int(dx), -int(dy))

            # Keep the rectangle within the image boundaries
            full_rect = QRect(
                0, 0, self.viewer.pixmap.width(), self.viewer.pixmap.height()
            )

            # Correct the left edge
            if new_rect.left() < full_rect.left():
                new_rect.moveLeft(full_rect.left())

            # Correct the right edge
            if new_rect.right() > full_rect.right():
                new_rect.moveRight(full_rect.right())

            # Correct the top edge
            if new_rect.top() < full_rect.top():
                new_rect.moveTop(full_rect.top())

            # Correct the bottom edge
            if new_rect.bottom() > full_rect.bottom():
                new_rect.moveBottom(full_rect.bottom())

            # Update view_rect
            self.viewer.view_rect = new_rect

            # Update the displayed image and visible layers
            self.viewer.layer_manager.update_display()

            # Set the new starting position for the next drag
            self.viewer.drag_start_pos = event.position()

    def mouseReleaseEvent(self, event):
        if self.viewer.selection_mode and event.button() == Qt.LeftButton:
            mapped_pos = self.map_to_pixmap_coordinates(event.position())
            self.viewer.end_point = mapped_pos
            self.viewer.selecting = False

            # Clear the temporary rectangle layer
            self.viewer.layer_manager.delete_layer("zoom_preview")
            self.viewer.layer_manager.update_display()

            # Perform the zoom
            self.viewer.zoom_to_selection()
            return

    def wheelEvent(self, event: QWheelEvent):
        if self.viewer.pixmap is None or self.viewer.pixmap.isNull():
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        self.viewer.zoom_by(1.2 ** (delta / 120), event.position())
        event.accept()

    def map_to_pixmap_coordinates(self, pos):
        pixmap = self.pixmap()
        if not pixmap:
            return pos
        label_size = self.size()
        pixmap_size = pixmap.size()
        offset_x = max(0, (label_size.width() - pixmap_size.width()) // 2)
        offset_y = max(0, (label_size.height() - pixmap_size.height()) // 2)
        mapped_x = pos.x() - offset_x
        mapped_y = pos.y() - offset_y

        # Correct relative to view_rect (for subsequent zoom operations)
        scale_x = self.viewer.view_rect.width() / self.viewer.scaled_pixmap.width()
        scale_y = self.viewer.view_rect.height() / self.viewer.scaled_pixmap.height()

        corrected_x = self.viewer.view_rect.x() + mapped_x * scale_x
        corrected_y = self.viewer.view_rect.y() + mapped_y * scale_y

        return QPointF(corrected_x, corrected_y)


class ImageViewer(QMainWindow):
    def __init__(self, project_path: pl.Path | None = None):
        super().__init__()

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.debug_mode = False
        self.__version__ = __version__
        self.__version_date__ = __version_date__

        grid = QGridLayout()
        grid.setSpacing(5)
        self.start_point = None
        self.end_point = None
        self.drag_start_pos = None
        self.selecting = False
        self.pixmap = None
        self.scaled_pixmap = None
        self.view_rect = QRect()

        # Initialize landmarks, semilandmarks, and scale
        self.scale = None
        self.scale_unit = ""
        self.angle_deg = 0
        self.nome_file = ""
        self.file_path = pl.Path("")
        self.code = ""
        self.mass_value = 0.0
        self.project_path: pl.Path | None = None

        self.landmark_names = []
        self.landmarks_groups = {}
        self.curves = {}
        self.main_axis = None
        self.reference_axis = None
        self.reference_axis_aligned = False
        self.coordinate_display_offset = (0.0, 0.0)
        self.raw_to_display_transform = None
        self.semilandmarks = {}
        self.landmarks = self.init_landmarks(self.landmark_names)
        self.landmarks_raw: dict | None = None

        self.scale_factor = 1

        # add a status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # add a label to status bar to show the current mode
        self.mode_label = QLabel("")
        self.status_bar.addPermanentWidget(self.mode_label)

        # self.plugin_calibrazione = CalibrationPlugin(self)
        self.plugin_arti = ArtiPlugin(self)

        self.image = ClickableLabel(self)

        self.image.setAlignment(Qt.AlignCenter)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.image)

        grid.addWidget(self.scroll_area, 0, 0, 6, 10)

        self.scaling_mode = QComboBox(self)
        self.scaling_mode.addItems(["Auto width", "Auto height", "Original size"])
        self.scaling_mode.setCurrentIndex(1)
        self.scale_label = QLabel("Image scale:")
        grid.addWidget(self.scale_label, 8, 0, 1, 1)
        grid.addWidget(self.scaling_mode, 8, 1, 1, 1)

        self.landmark_combo = QComboBox()
        self.landmark_combo.addItems(self.landmark_names)
        grid.addWidget(QLabel("Landmarks"), 8, 2, 1, 1)
        grid.addWidget(self.landmark_combo, 8, 3, 1, 1)

        self.reset_button = QPushButton("Reset positions")
        self.reset_button.clicked.connect(self.reset)
        grid.addWidget(self.reset_button, 8, 4, 1, 1)

        self.selection_mode = False

        self.central_widget.setLayout(grid)
        self.setWindowTitle("SMORPHILA - Data acquisition")
        self.resize(1000, 700)

        self.menu_bar = QMenuBar(self)
        self.setMenuBar(self.menu_bar)

        file_menu = QMenu("File", self)
        edit_menu = QMenu("Edit", self)
        landmarks_menu = QMenu("Landmarks", self)
        view_menu = QMenu("View", self)

        self.menu_bar.addMenu(file_menu)
        self.menu_bar.addMenu(edit_menu)
        self.menu_bar.addMenu(landmarks_menu)
        self.menu_bar.addMenu(view_menu)

        open_action = QAction("Open image", self)
        open_action.triggered.connect(self.load)
        file_menu.addAction(open_action)

        save_data_action = QAction("Save data", self)
        save_data_action.setShortcut("Ctrl+S")
        save_data_action.triggered.connect(self.save_data)
        file_menu.addAction(save_data_action)

        constrained_landmarks_action = QAction("Show constrained landmarks", self)
        constrained_landmarks_action.setCheckable(True)
        constrained_landmarks_action.setChecked(True)
        constrained_landmarks_action.triggered.connect(
            lambda visible: self._set_layer_visibility("landmarks", visible)
        )
        raw_landmarks_action = QAction("Show raw landmarks", self)
        raw_landmarks_action.setCheckable(True)
        raw_landmarks_action.triggered.connect(
            lambda visible: self._set_layer_visibility("landmarks_raw", visible)
        )
        view_menu.addAction(constrained_landmarks_action)
        view_menu.addAction(raw_landmarks_action)

        zoom_in_action = QAction("Zoom in", self)
        zoom_out_action = QAction("Zoom out", self)
        fit_image_action = QAction("Fit image", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_out_action.setShortcut("Ctrl+-")
        fit_image_action.setShortcut("Ctrl+0")
        zoom_in_action.triggered.connect(lambda: self.zoom_by(1.2))
        zoom_out_action.triggered.connect(lambda: self.zoom_by(1 / 1.2))
        fit_image_action.triggered.connect(self.reset_view_rect)
        view_menu.addAction(zoom_in_action)
        view_menu.addAction(zoom_out_action)
        view_menu.addAction(fit_image_action)

        # Plugins: layer manager and tools
        self.layer_manager = LayerManager(self)
        self.spezzata_plugin = SpezzataAligner(self)
        self.insert_landmarks = LandmarkPlugin(self)
        self.image_aligner = ImageAligner(self)
        self.rileva_contorno = ContourPlugin(self)
        self.spezzata_curva = SpezzataCurva(self)
        self.calibrazione = CalibrationPlugin(self)
        self.gestione_layers = LayerPlugin(self)

        # Add plugin to the Landmarks menu
        spezzata_action = QAction("Align polyline (CTRL+I)", self)
        spezzata_action.triggered.connect(self.spezzata_plugin.start)
        landmarks_menu.addAction(spezzata_action)

        # Add plugin to the Landmarks menu
        arti_action = QAction("Create idealized polyline", self)
        arti_action.triggered.connect(self.plugin_arti.activate)
        landmarks_menu.addAction(arti_action)

        # Add plugin to the Landmarks menu
        landmarks_action = QAction("Add landmarks (CTRL+L)", self)
        landmarks_action.triggered.connect(self.insert_landmarks.activate)
        landmarks_menu.addAction(landmarks_action)

        # Add plugin to the Landmarks menu
        contour_action = QAction("Find contours", self)
        contour_action.triggered.connect(self.rileva_contorno.extract_contours)
        landmarks_menu.addAction(contour_action)

        # Add plugin to the Landmarks menu
        spezzatacurva_action = QAction("Manual semilandmarks", self)
        spezzatacurva_action.triggered.connect(self.spezzata_curva.start)
        landmarks_menu.addAction(spezzatacurva_action)

        # Add plugin to the Edit menu
        rotate_action = QAction("Rotate image", self)
        rotate_action.triggered.connect(self.rotate_image_dialog)
        edit_menu.addAction(rotate_action)

        # Add plugin to the Edit menu
        align_action = QAction("Align image", self)
        align_action.triggered.connect(self.image_aligner.align_image)
        edit_menu.addAction(align_action)

        # Add calibration plugin
        calibrazione_action = QAction("Calibrate scale", self)
        calibrazione_action.triggered.connect(self.calibrazione.activate)
        edit_menu.addAction(calibrazione_action)

        # Add layer management plugin
        gestisci_action = QAction("Manage layers", self)
        gestisci_action.triggered.connect(self.gestione_layers.activate)
        view_menu.addAction(gestisci_action)

        # SHORTCUTS

        # Ctrl+L -> activate landmarks
        shortcut_landmark = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut_landmark.activated.connect(self.insert_landmarks.activate)

        # Ctrl+I -> align polyline
        shortcut_landmark = QShortcut(QKeySequence("Ctrl+I"), self)
        shortcut_landmark.activated.connect(self.spezzata_plugin.start)

        #  "1" → zoom in
        zoom_in_shortcut = QShortcut(QKeySequence("1"), self)
        zoom_in_shortcut.setContext(Qt.ApplicationShortcut)
        zoom_in_shortcut.activated.connect(lambda: self.zoom_plus(1.1))

        #  "+" → zoom in
        zoom_in_shortcut2 = QShortcut(QKeySequence("+"), self)
        zoom_in_shortcut2.setContext(Qt.ApplicationShortcut)
        zoom_in_shortcut2.activated.connect(lambda: self.zoom_plus(1.1))

        #  "0" → zoom out
        shortcut_zoom_out = QShortcut(QKeySequence("0"), self)
        shortcut_zoom_out.activated.connect(lambda: self.zoom_plus(0.9))

        #  "-" → zoom out
        shortcut_zoom_out2 = QShortcut(QKeySequence("-"), self)
        shortcut_zoom_out2.activated.connect(lambda: self.zoom_plus(0.9))

        # Esc -> deactivate everything
        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self.disattiva_tutti_i_plugin)

        # Arrow key shortcuts
        shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self)
        shortcut_left.activated.connect(lambda: self.move_view_rect(-1, 0))

        shortcut_right = QShortcut(QKeySequence(Qt.Key_Right), self)
        shortcut_right.activated.connect(lambda: self.move_view_rect(1, 0))

        shortcut_up = QShortcut(QKeySequence(Qt.Key_Up), self)
        shortcut_up.activated.connect(lambda: self.move_view_rect(0, -1))

        shortcut_down = QShortcut(QKeySequence(Qt.Key_Down), self)
        shortcut_down.activated.connect(lambda: self.move_view_rect(0, 1))

        # Give focus to a widget that can receive events
        self.central_widget.setFocusPolicy(Qt.StrongFocus)
        self.central_widget.setFocus()

        self.show()
        QTimer.singleShot(500, lambda: print("Initial focus:", self.focusWidget()))
        if project_path is not None:
            QTimer.singleShot(0, lambda: self._load_project_path(project_path))

    def move_view_rect(self, dx, dy):
        if not hasattr(self, "view_rect") or self.view_rect is None:
            return
        step = int(self.view_rect.width() * 0.1)
        dx *= step
        dy *= step
        # Create a copy of the current rectangle
        new_rect = QRect(self.view_rect)

        # Move the rectangle
        new_rect.translate(dx, dy)

        # Constrain the rectangle to the image boundaries
        full_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        new_rect = new_rect.intersected(full_rect)

        # Apply the new view rectangle
        self.set_view_rect(new_rect)
        self.layer_manager.update_display()

    @staticmethod
    def _read_project(project_path):
        """Read a landmark-editor TOML project into viewer structures."""
        try:
            data = tomllib.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ValueError(f"Could not read project: {error}") from error
        names = data.get("landmark_names", [])
        if not isinstance(names, list) or not all(
            isinstance(name, str) for name in names
        ):
            raise ValueError("landmark_names must be an array of strings")
        positions = data.get("landmark_positions", {})
        if not isinstance(positions, dict):
            raise ValueError("landmark_positions must be a table")
        landmarks = {name: {"coordinates": [], "color": None} for name in names}
        for name, position in positions.items():
            if name not in landmarks:
                landmarks[name] = {"coordinates": [], "color": None}
            coordinates = (
                position.get("coordinates") if isinstance(position, dict) else None
            )
            if coordinates is None:
                continue
            if (
                not isinstance(coordinates, list)
                or len(coordinates) != 2
                or not all(isinstance(value, (int, float)) for value in coordinates)
            ):
                raise ValueError(
                    f"Coordinates for landmark '{name}' must contain two numbers"
                )
            landmarks[name]["coordinates"] = coordinates
        groups_data = data.get("landmarks_groups", {})
        if not isinstance(groups_data, dict):
            raise ValueError("landmarks_groups must be a table")
        groups = {}
        for group_name, group_data in groups_data.items():
            if not isinstance(group_data, dict):
                raise ValueError(f"Group '{group_name}' must be a table")
            segments = group_data.get("segments")
            if segments is None:
                legacy = group_data.get("landmarks", [])
                if not isinstance(legacy, list) or not all(
                    isinstance(name, str) for name in legacy
                ):
                    raise ValueError(
                        f"Landmarks for group '{group_name}' must be strings"
                    )
                segments = [list(pair) for pair in zip(legacy, legacy[1:])]
            if not isinstance(segments, list):
                raise ValueError(f"Segments for group '{group_name}' must be an array")
            normalized = []
            for segment in segments:
                if (
                    not isinstance(segment, list)
                    or len(segment) != 2
                    or not all(isinstance(name, str) for name in segment)
                ):
                    raise ValueError(
                        f"Each segment in group '{group_name}' must contain two landmarks"
                    )
                normalized.append(segment)
            groups[group_name] = {
                "segments": normalized,
                "angles": group_data.get("angles", []),
            }
        ordered_names = names + [name for name in landmarks if name not in names]
        return (
            ordered_names,
            landmarks,
            groups,
        )

    @staticmethod
    def _read_unified_project(project_path: pl.Path):
        """Read landmark definitions from a unified SMORPHILA project."""

        project = load_project(project_path)
        definitions = project["definitions"]
        landmarks_data = definitions.get("landmarks", {})
        if not isinstance(landmarks_data, dict):
            raise ValueError("definitions.landmarks must be an object")
        names = list(landmarks_data)
        landmarks = {name: {"coordinates": [], "color": None} for name in names}
        groups_data = definitions.get("landmarks_groups", {})
        if not isinstance(groups_data, dict):
            raise ValueError("definitions.landmarks_groups must be an object")
        groups = {}
        for group_name, group_data in groups_data.items():
            if not isinstance(group_data, dict):
                raise ValueError(f"Group '{group_name}' must be an object")
            segments = group_data.get("segments", [])
            if not isinstance(segments, list):
                raise ValueError(f"Segments for group '{group_name}' must be an array")
            if any(
                not isinstance(segment, list)
                or len(segment) != 2
                or not all(isinstance(name, str) for name in segment)
                for segment in segments
            ):
                raise ValueError(
                    f"Each segment in group '{group_name}' must contain two landmarks"
                )
            groups[group_name] = {
                "segments": segments,
                "angles": group_data.get("angles", []),
            }
        curves_data = definitions.get("curves", {})
        if not isinstance(curves_data, dict):
            raise ValueError("definitions.curves must be an object")
        curves = {}
        for curve_name, curve_data in curves_data.items():
            if not isinstance(curve_data, dict):
                raise ValueError(f"Curve '{curve_name}' must be an object")
            point_count = curve_data.get("point_count")
            start_landmark = curve_data.get("start_landmark")
            end_landmark = curve_data.get("end_landmark")
            if (
                isinstance(point_count, bool)
                or not isinstance(point_count, int)
                or point_count < 2
            ):
                raise ValueError(
                    f"Curve '{curve_name}' must define at least two intervals"
                )
            if not isinstance(start_landmark, str) or not isinstance(end_landmark, str):
                raise ValueError(f"Curve '{curve_name}' anchors must be landmark names")
            if start_landmark == end_landmark:
                raise ValueError(f"Curve '{curve_name}' must use two different anchors")
            if start_landmark not in landmarks or end_landmark not in landmarks:
                raise ValueError(f"Curve '{curve_name}' references an unknown landmark")
            curves[curve_name] = {
                "point_count": point_count,
                "start_landmark": start_landmark,
                "end_landmark": end_landmark,
            }
        return names, landmarks, groups, definitions.get("reference_axis"), curves

    def load_project(self):
        project_name, _ = QFileDialog.getOpenFileName(
            self, "Load project", "", "Projects (*.json *.toml);;All files (*)"
        )
        if not project_name:
            return
        self._load_project_path(pl.Path(project_name))

    def _load_project_path(self, project_path: pl.Path):
        try:
            if project_path.suffix.lower() == ".json":
                (
                    names,
                    landmarks,
                    groups,
                    reference_axis,
                    curves,
                ) = self._read_unified_project(project_path)
            else:
                names, landmarks, groups = self._read_project(project_path)
                reference_axis = None
                curves = {}
        except (TypeError, ValueError) as error:
            QMessageBox.critical(self, "Load project", str(error))
            return
        self.landmark_names = names
        self.landmarks_groups = groups
        self.reference_axis = reference_axis
        self.curves = curves
        self.semilandmarks = {
            name: {
                "landmarks": [curve["start_landmark"], curve["end_landmark"]],
                "nsemilandmarks": [curve["point_count"]],
                "coordinates": [],
            }
            for name, curve in curves.items()
        }
        self.landmarks = landmarks
        self.landmark_combo.clear()
        self.landmark_combo.addItems(self.landmark_names)
        self.project_path = (
            project_path if project_path.suffix.lower() == ".json" else None
        )
        self.layer_manager.update_display()
        self.status_bar.showMessage(f"Project loaded: {project_path.name}")

    def load(self):
        initial_directory = ""
        if self.project_path is not None:
            images_directory = self.project_path.parent / "images"
            initial_directory = str(
                images_directory
                if images_directory.is_dir()
                else self.project_path.parent
            )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an image",
            initial_directory,
            f"Images ({IMAGE_EXTENSION});;All files (*)",
        )
        if not file_path:
            return
        self.glb = [file_path]
        self.idx = 0
        individual_data = self._individual_for_image(pl.Path(file_path))
        self.load_image(self.glb[self.idx])
        if individual_data is not None:
            self._load_individual_data(individual_data)
            self.status_bar.showMessage(
                f"Image loaded: {self.code} (project data found)"
            )
        elif pl.Path(file_path).with_suffix(".json").is_file():
            self.load_json(pl.Path(file_path).with_suffix(".json"))

            self.status_bar.showMessage(f"Image loaded: {self.code} (json file found)")

        else:
            self.status_bar.showMessage(
                f"Image loaded: {self.code} (no json file found)"
            )

        self.setWindowTitle(f"SMORPHILA - Data acquisition - {pl.Path(file_path).name}")

    def apply_reference_axis_alignment(self) -> bool:
        """Align all placed landmarks using the configured reference axis."""

        if self.reference_axis_aligned:
            return True
        axis = self.reference_axis
        if not isinstance(axis, dict):
            return True
        landmark_names = axis.get("landmarks")
        if (
            not isinstance(landmark_names, list)
            or len(landmark_names) != 2
            or not all(isinstance(name, str) for name in landmark_names)
        ):
            return True
        if any(
            not self.landmarks.get(name, {}).get("coordinates")
            for name in landmark_names
        ):
            QMessageBox.warning(
                self,
                "Reference axis",
                "Place both reference-axis landmarks before creating the idealized polyline.",
            )
            return False
        self.image_aligner.align_project_reference_axis(landmark_names)
        self.reference_axis_aligned = True
        return True

    def load_json(self, file_path):
        """Load a legacy individual JSON file."""
        with open(file_path, "r") as file_in:
            d = json.load(file_in)
        self._load_individual_data(d)

    def _individual_for_image(self, image_path: pl.Path):
        """Return the unified-project record associated with an image, if any."""

        if self.project_path is None:
            return None
        try:
            project = load_project(self.project_path)
            resolved_image = image_path.resolve()
            for individual_data in project["individuals"].values():
                stored_path = individual_data.get("image_path")
                if not isinstance(stored_path, str):
                    continue
                candidate = (self.project_path.parent / stored_path).resolve()
                if candidate == resolved_image:
                    return individual_data
        except (OSError, ValueError):
            return None
        return None

    def _load_individual_data(self, d):
        """Load one individual record from either supported JSON format."""

        self.scale = d["scale"]
        self.scale_unit = d["scale_unit"]

        self.code = d["code"]
        self.mass_value = d["mass_value"]
        landmarks_json = d["landmarks"]
        raw_landmarks = d.get("landmarks_raw", landmarks_json)
        if not isinstance(raw_landmarks, dict):
            raw_landmarks = landmarks_json
        self.landmarks_raw = copy.deepcopy(raw_landmarks)
        rebuild_idealized_polyline = isinstance(self.reference_axis, dict) and bool(
            self.landmarks_groups
        )
        loaded_landmarks = (
            raw_landmarks if rebuild_idealized_polyline else landmarks_json
        )
        self.layer_manager.create_layer("landmarks")
        self.layer_manager.create_layer("landmarks_raw")
        self.layer_manager.visible["landmarks"] = True
        self.layer_manager.visible["landmarks_raw"] = False

        # Make it possible to add or remove landmarks
        for key in self.landmarks:
            if key in loaded_landmarks:
                self.landmarks[key] = copy.deepcopy(loaded_landmarks[key])
            else:
                self.landmarks[key] = {"coordinates": None, "color": None}

        self.semilandmarks_json = d.get("semilandmarks", {})
        if not isinstance(self.semilandmarks_json, dict):
            self.semilandmarks_json = {}

        for key, semilandmark in self.semilandmarks.items():
            saved_semilandmark = self.semilandmarks_json.get(key)
            if not isinstance(saved_semilandmark, dict):
                continue
            if semilandmark["landmarks"] != saved_semilandmark.get("landmarks"):
                continue
            coordinates = saved_semilandmark.get("coordinates", [])
            if not isinstance(coordinates, list):
                continue
            semilandmark["coordinates"] = coordinates
            self.layer_manager.create_layer("semilandmarks")

        if rebuild_idealized_polyline:
            self.angle_deg = 0
            self.reference_axis_aligned = False
            self.coordinate_display_offset = (0.0, 0.0)
            self.raw_to_display_transform = None
            self.plugin_arti.activate()
        else:
            self.angle_deg = 0
            self.rotate_angle(d["angle_deg"])
            self.reference_axis_aligned = bool(d.get("reference_axis_aligned", False))
            self.coordinate_display_offset = tuple(
                d.get("coordinate_display_offset", [0.0, 0.0])
            )
            self.raw_to_display_transform = d.get("raw_to_display_transform")

        if self.scale:
            self.scale_label.setText(f"Scale: {self.scale:.4f} {self.scale_unit}/px")

    def _set_layer_visibility(self, name: str, visible: bool):
        if name in self.layer_manager.layers:
            self.layer_manager.visible[name] = visible
            self.layer_manager.update_display()

    def load_image(self, file_name):
        self.reset_all()
        self.reference_axis_aligned = False
        self.landmarks_raw = None
        self.coordinate_display_offset = (0.0, 0.0)
        self.raw_to_display_transform = None
        self.pixmap = QPixmap()
        self.pixmap.load(str(file_name))

        self.view_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        mode = self.scaling_mode.currentText()
        screen_geom = self.screen().availableGeometry()
        if mode == "Auto width":
            target_width = int(screen_geom.width() * 0.7)
            scaled_pixmap = self.pixmap.scaledToWidth(
                target_width, Qt.SmoothTransformation
            )
        elif mode == "Auto height":
            target_height = int(screen_geom.height() * 0.6)
            scaled_pixmap = self.pixmap.scaledToHeight(
                target_height, Qt.SmoothTransformation
            )
        else:
            scaled_pixmap = self.pixmap

        self.scaled_pixmap = scaled_pixmap

        self.image.setPixmap(scaled_pixmap)
        self.nome_file = pl.Path(file_name).name
        self.DIR_PNG = pl.Path(file_name).parent
        self.file_path = pl.Path(file_name)

        self.scale_label.setText("")

    def init_landmarks(self, names):
        """
        Initialize the landmark structure from a list of names.
        Each landmark has: coordinates=[], color=None
        """

        self.landmarks = {name: {"coordinates": [], "color": None} for name in names}
        return self.landmarks

    def rotate_image_dialog(self):
        """
        Ask for the image rotation angle
        """
        angle, ok = QInputDialog.getDouble(
            self, "Rotate image", "Angle (degrees):", 0.0, -360.0, 360.0, 1
        )
        if ok:
            self.rotate_angle(angle)

    def rotate_angle(self, angle):
        """
        Rotate the image by an arbitrary angle
        """
        transform = QTransform()
        transform.rotate(angle)

        rotated_pixmap = self.pixmap.transformed(transform, Qt.SmoothTransformation)
        container_size = self.scroll_area.viewport().size()
        scaled_rotated = rotated_pixmap.scaled(
            container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.scaled_pixmap = scaled_rotated
        self.pixmap = rotated_pixmap  # also update the original
        self.image.setPixmap(scaled_rotated)
        self.reset_view_rect()
        if self.angle_deg:
            self.angle_deg += angle
        else:
            self.angle_deg = angle
        self.layer_manager.update_display()

        print(f"{self.angle_deg=}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "scaled_pixmap") and self.scaled_pixmap:
            self.layer_manager.update_display()

    def set_view_rect(self, sel_rect):
        # Compute the container ratio
        container_size = self.scroll_area.viewport().size()
        container_ratio = container_size.width() / container_size.height()
        sel_ratio = sel_rect.width() / sel_rect.height() if sel_rect.height() > 0 else 1

        adjusted_rect = QRect(sel_rect)
        if sel_ratio < container_ratio:
            new_width = sel_rect.height() * container_ratio
            dx = int((new_width - sel_rect.width()) / 2)
            adjusted_rect.adjust(-dx, 0, dx, 0)
        else:
            new_height = sel_rect.width() / container_ratio
            dy = int((new_height - sel_rect.height()) / 2)
            adjusted_rect.adjust(0, -dy, 0, dy)

        # Intersect with the image (constrain to boundaries)
        full_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        self.view_rect = adjusted_rect.intersected(full_rect)

        # Show the new portion
        cropped = self.pixmap.copy(self.view_rect)
        scaled = cropped.scaled(
            container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.scaled_pixmap = scaled

        self.image.setPixmap(scaled)

    def zoom_to_selection(self):
        if self.start_point is None or self.end_point is None:
            return

        x1, y1 = self.start_point.x(), self.start_point.y()
        x2, y2 = self.end_point.x(), self.end_point.y()

        sel_rect_original = QRect(
            int(min(x1, x2)), int(min(y1, y2)), int(abs(x2 - x1)), int(abs(y2 - y1))
        )

        # Intersect with the original image boundaries
        full_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        corrected_rect = sel_rect_original.intersected(full_rect)

        self.set_view_rect(corrected_rect)
        self.layer_manager.update_display()

    def zoom_by(self, factor, anchor=None):
        if not hasattr(self, "pixmap") or self.pixmap.isNull():
            return

        if factor <= 0:
            return
        if anchor is None:
            anchor = QPointF(self.image.width() / 2, self.image.height() / 2)
        anchor_image = self.image.map_to_pixmap_coordinates(anchor)
        if self.scaled_pixmap.isNull() or self.view_rect.isEmpty():
            return
        relative_x = (anchor_image.x() - self.view_rect.x()) / self.view_rect.width()
        relative_y = (anchor_image.y() - self.view_rect.y()) / self.view_rect.height()
        zoom_level = getattr(self, "zoom_factor", 1.0)
        zoom_level = max(0.25, min(20.0, zoom_level * factor))
        new_width = max(1, int(self.pixmap.width() / zoom_level))
        new_height = max(1, int(self.pixmap.height() / zoom_level))
        new_x = int(anchor_image.x() - relative_x * new_width)
        new_y = int(anchor_image.y() - relative_y * new_height)
        new_rect = QRect(new_x, new_y, new_width, new_height)

        self.set_view_rect(new_rect)
        self.zoom_factor = zoom_level

        self.layer_manager.update_display()

    def zoom_plus(self, factor):
        """Backward-compatible center zoom used by the existing shortcuts."""
        self.zoom_by(factor)

    def reset_view_rect(self):
        if self.pixmap:
            self.zoom_factor = 1.0
            self.view_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
            container_size = self.scroll_area.viewport().size()
            cropped = self.pixmap.copy(self.view_rect)
            scaled = cropped.scaled(
                container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.scaled_pixmap = scaled
            self.image.setPixmap(scaled)
            self.disattiva_zoom()

    def disattiva_zoom(self):
        self.selection_mode = False
        if self.insert_landmarks.active or self.spezzata_plugin.active:
            self.image.setCursor(Qt.CrossCursor)

    def reset(self):
        self.init_landmarks(self.landmark_names)
        self.layer_manager.update_display()

    def save_data(self):
        save_data.save_data_json(self)

    def show_working_message(self):
        QMessageBox.information(self, "Info", "Working in progress")

    def disattiva_tutti_i_plugin(self):
        self.insert_landmarks.deactivate()
        self.spezzata_plugin.active = False
        self.spezzata_curva.active = False
        self.image_aligner.active = False
        self.selection_mode = False
        self.calibrazione.deactivate()
        # Set the QLabel cursor
        self.image.setCursor(Qt.ArrowCursor)

        # Also set the global cursor
        QApplication.setOverrideCursor(Qt.ArrowCursor)

    def reset_all(self):
        print("[reset_all] Global reset in progress...")

        # Clear the displayed image
        self.image.clear()
        self.pixmap = None
        self.scaled_pixmap = None
        self.view_rect = QRect()

        # Reset selection, zoom, and drag
        self.start_point = None
        self.end_point = None
        self.drag_start_pos = None
        self.selecting = False
        self.scale_factor = 1
        self.zoom_factor = 1.0
        self.scale = None
        self.scale_unit = ""

        self.angle_deg = 0

        # Scrollbar: reset position
        self.scroll_area.horizontalScrollBar().setValue(0)
        self.scroll_area.verticalScrollBar().setValue(0)

        # Reset ComboBox
        self.landmark_combo.setCurrentIndex(0)
        self.scaling_mode.setCurrentIndex(1)

        # State
        self.selection_mode = False

        # Layers: clear everything
        if self.layer_manager:
            self.layer_manager.clear_all_layers()  # clear_all_layers must be implemented in layer_manager

        # Landmarks: reset the structure
        self.init_landmarks(self.landmark_names)

        # Deactivate plugins
        self.disattiva_tutti_i_plugin()

        # Update the display
        self.layer_manager.update_display()

        print("[reset_all] Completed")


def run():
    app = QApplication(sys.argv)
    project_path = pl.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    viewer = ImageViewer(project_path)
    # if len(sys.argv) > 1:
    #    viewer

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
