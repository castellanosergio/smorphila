"""
main program of geomorfometria package
"""

import sys
import pathlib as pl
import json


from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QComboBox,
    QPushButton,
    QMessageBox,
    QGridLayout,
    QFileDialog,
    QScrollArea,
    QMainWindow,
    QMenuBar,
    QMenu,
    QInputDialog,
    QStatusBar,
)
from PySide6.QtGui import QAction, QPixmap, QTransform, QCursor
from PySide6.QtCore import Qt, QPoint, QRect, QEvent, QPointF, QTimer
from PySide6.QtGui import QKeySequence, QShortcut


from .layer_manager import LayerManager
from .plugin_allinea_spezzata import SpezzataAligner
from .inserisci_landmarks import LandmarkPlugin
from .image_aligner import ImageAligner
from .plugin_arti import ArtiPlugin
from .rileva_contorno import ContourPlugin
from .plugin_spezzata_curva import SpezzataCurva
from .plugin_calibrazione import CalibrationPlugin
from .plugin_gestione_layers import LayerPlugin
from . import save_data
from . import settings_landmarks

__version__ = "0.0.4"
__version_date__ = "2025-05-28"
IMAGE_EXTENSION = "*.jpg *.JPG *.png *.PNG"


class ClickableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewer = parent
        self.setFocusPolicy(Qt.StrongFocus)

    def enterEvent(self, event):
        if self.viewer.inserisci_landmarks.active or self.viewer.spezzata_curva.active or self.viewer.calibrazione.active:
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

        elif self.viewer.inserisci_landmarks.active:
            mapped = self.map_to_pixmap_coordinates(event.position())
            name = self.viewer.landmark_combo.currentText()

            self.viewer.inserisci_landmarks.handle_click(name, mapped)
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
            p1 = QPoint(int(self.viewer.start_point.x()), int(self.viewer.start_point.y()))
            p2 = QPoint(int(self.viewer.end_point.x()), int(self.viewer.end_point.y()))
            top_left = QPoint(min(p1.x(), p2.x()), min(p1.y(), p2.y()))
            bottom_right = QPoint(max(p1.x(), p2.x()), max(p1.y(), p2.y()))
            rect = QRect(top_left, bottom_right)
            self.viewer.layer_manager.clear_layer("zoom_preview")
            self.viewer.layer_manager.draw_rect("zoom_preview", rect)
            self.viewer.layer_manager.update_display()

        elif not self.viewer.selection_mode and event.buttons() == Qt.LeftButton:
            print(f"{self.viewer.selection_mode=}")

            if self.viewer.inserisci_landmarks.active or self.viewer.spezzata_curva.active:
                print("RETURN")
                return

            if not hasattr(self.viewer, "view_rect") or self.viewer.drag_start_pos is None:
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
            full_rect = QRect(0, 0, self.viewer.pixmap.width(), self.viewer.pixmap.height())

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

            # Update the displayed image
            container_size = self.viewer.scroll_area.viewport().size()
            cropped = self.viewer.pixmap.copy(self.viewer.view_rect)
            scaled = cropped.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.viewer.scaled_pixmap = scaled
            self.setPixmap(scaled)

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
    def __init__(self):
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

        # Initialize landmarks, semilandmarks, and scale
        self.scale = None
        self.scale_unit = ""
        self.angle_deg = 0
        self.nome_file = ""
        self.file_path = pl.Path("")
        self.code = ""
        self.mass_value = 0.0

        self.landmark_names = settings_landmarks.landmark_names

        self.landmarks_groups = settings_landmarks.landmarks_groups

        self.semilandmarks = settings_landmarks.semilandmarks
        print(self.semilandmarks)
        self.landmarks = self.init_landmarks(self.landmark_names)

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
        self.activate_selector_button = QPushButton("Zoom")
        self.activate_selector_button.setCheckable(True)
        self.activate_selector_button.clicked.connect(self.toggle_selection_mode)
        grid.addWidget(self.activate_selector_button, 8, 5, 1, 1)

        self.zoom_out_button = QPushButton("Zoom out")
        self.zoom_out_button.clicked.connect(self.reset_view_rect)
        grid.addWidget(self.zoom_out_button, 8, 6, 1, 1)

        self.save_data_button = QPushButton("Save data")
        self.save_data_button.clicked.connect(self.save_data)
        grid.addWidget(self.save_data_button, 8, 9, 1, 1)

        self.central_widget.setLayout(grid)
        self.setWindowTitle(f"Morphometric analysis - v. {__version__} {__version_date__}")
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

        toggle_layer_action = QAction("Show/Hide landmarks", self)
        toggle_layer_action.triggered.connect(lambda: self.layer_manager.toggle_visibility("landmarks"))
        view_menu.addAction(toggle_layer_action)

        # Plugins: layer manager and tools
        self.layer_manager = LayerManager(self)
        self.spezzata_plugin = SpezzataAligner(self)
        self.inserisci_landmarks = LandmarkPlugin(self)
        self.image_aligner = ImageAligner(self)
        self.rileva_contorno = ContourPlugin(self)
        self.spezzata_curva = SpezzataCurva(self)
        self.calibrazione = CalibrationPlugin(self)
        self.gestione_layers = LayerPlugin(self)

        # Add plugin to the Landmarks menu
        spezzata_action = QAction("Align polyline (CTRL+S)", self)
        spezzata_action.triggered.connect(self.spezzata_plugin.start)
        landmarks_menu.addAction(spezzata_action)

        # Add plugin to the Landmarks menu
        arti_action = QAction("Create idealized polyline", self)
        arti_action.triggered.connect(self.plugin_arti.activate)
        landmarks_menu.addAction(arti_action)

        # Add plugin to the Landmarks menu
        landmarks_action = QAction("Add landmarks (CTRL+L)", self)
        landmarks_action.triggered.connect(self.inserisci_landmarks.activate)
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
        shortcut_landmark.activated.connect(self.inserisci_landmarks.activate)

        # Ctrl+S -> activate landmarks
        shortcut_landmark = QShortcut(QKeySequence("Ctrl+S"), self)
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

    def load(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an image",
            "",
            f"Images ({IMAGE_EXTENSION});;All files (*)",
        )
        if not file_path:
            return
        self.glb = [file_path]
        self.idx = 0
        self.load_image(self.glb[self.idx])

        # check if JSON file is present
        if pl.Path(file_path).with_suffix(".json").is_file():
            self.load_json(pl.Path(file_path).with_suffix(".json"))

            self.status_bar.showMessage(f"Image loaded: {self.code} (json file found)")

        else:
            self.status_bar.showMessage(f"Image loaded: {self.code} (no json file found)")

        self.setWindowTitle(f"{pl.Path(file_path).name} - Morphometric analysis - v. {__version__}")

    def load_json(self, file_path):
        """
        load json file
        """
        with open(file_path, "r") as file_in:
            d = json.load(file_in)

        self.scale = d["scale"]
        self.scale_unit = d["scale_unit"]

        self.code = d["code"]
        self.mass_value = d["mass_value"]
        landmarks_json = d["landmarks"]

        # Make it possible to add or remove landmarks
        for key in self.landmarks:
            if key in landmarks_json:
                self.landmarks[key] = landmarks_json[key]
                if self.landmarks[key]["coordinates"] != None:
                    check = 1
            else:
                self.landmarks[key] = {"coordinates": None, "color": None}
            if check == 1:
                self.layer_manager.create_layer("landmarks")

        self.semilandmarks_json = d["semilandmarks"]
        # Make it possible to add or remove semilandmarks

        for key in self.semilandmarks:
            if self.semilandmarks[key]["landmarks"] == self.semilandmarks_json[key]["landmarks"]:
                coord = self.semilandmarks_json[key].get("coordinates", [])
                self.semilandmarks[key]["coordinates"] = coord

                self.layer_manager.create_layer("semilandmarks")

        # rotation
        self.angle_deg = 0
        self.rotate_angle(d["angle_deg"])

        if self.scale:
            self.scale_label.setText(f"Scale: {self.scale:.4f} {self.scale_unit}/px")

    def load_image(self, file_name):
        self.reset_all()
        self.pixmap = QPixmap()
        self.pixmap.load(file_name)

        self.view_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        mode = self.scaling_mode.currentText()
        screen_geom = self.screen().availableGeometry()
        if mode == "Auto width":
            target_width = int(screen_geom.width() * 0.7)
            scaled_pixmap = self.pixmap.scaledToWidth(target_width, Qt.SmoothTransformation)
        elif mode == "Auto height":
            target_height = int(screen_geom.height() * 0.6)
            scaled_pixmap = self.pixmap.scaledToHeight(target_height, Qt.SmoothTransformation)
        else:
            scaled_pixmap = self.pixmap

        self.scaled_pixmap = scaled_pixmap

        self.image.setPixmap(scaled_pixmap)
        self.nome_file = pl.Path(file_name).name
        self.DIR_PNG = pl.Path(file_name).parent
        self.file_path = pl.Path(file_name)

        self.scale_label.setText("")

    def init_landmarks(self, nomi):
        """
        Initialize the landmark structure from a list of names.
        Each landmark has: coordinates=[], color=None
        """

        self.landmarks = {nome: {"coordinates": [], "color": None} for nome in nomi}
        return self.landmarks

    def rotate_image_dialog(self):
        """
        Ask for the image rotation angle
        """
        angle, ok = QInputDialog.getDouble(self, "Rotate image", "Angle (degrees):", 0.0, -360.0, 360.0, 1)
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
        scaled_rotated = rotated_pixmap.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        scaled = cropped.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.scaled_pixmap = scaled

        self.image.setPixmap(scaled)

    def zoom_to_selection(self):
        if self.start_point is None or self.end_point is None:
            return

        x1, y1 = self.start_point.x(), self.start_point.y()
        x2, y2 = self.end_point.x(), self.end_point.y()

        sel_rect_original = QRect(int(min(x1, x2)), int(min(y1, y2)), int(abs(x2 - x1)), int(abs(y2 - y1)))

        # Intersect with the original image boundaries
        full_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        corrected_rect = sel_rect_original.intersected(full_rect)

        self.set_view_rect(corrected_rect)
        self.layer_manager.update_display()

    def zoom_plus(self, factor):
        if not hasattr(self, "pixmap") or self.pixmap.isNull():
            print("No image loaded; cannot zoom")
            return

        print(f"[zoom_plus] called with factor = {factor}, scale_factor = {self.scale_factor}")

        # Scrollbar and viewport
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        viewport_size = self.scroll_area.viewport().size()

        # Coordinates of the visible center in the viewport
        cx = h_bar.value() + viewport_size.width() // 2
        cy = v_bar.value() + viewport_size.height() // 2

        # Correct for the inner margin in the QLabel (centering)
        label_size = self.image.size()
        pixmap_size = self.scaled_pixmap.size()
        offset_x = max(0, (label_size.width() - pixmap_size.width()) // 2)
        offset_y = max(0, (label_size.height() - pixmap_size.height()) // 2)
        cx -= offset_x
        cy -= offset_y

        # Convert to original image coordinates
        scale_x = self.view_rect.width() / self.scaled_pixmap.width()
        scale_y = self.view_rect.height() / self.scaled_pixmap.height()
        center_x = self.view_rect.x() + cx * scale_x
        center_y = self.view_rect.y() + cy * scale_y

        # Desired new size
        new_width = self.view_rect.width() / factor
        new_height = self.view_rect.height() / factor

        # Minimum limits: prevent the rectangle from becoming too small
        if factor < 1.0:
            min_rect_width = self.scroll_area.viewport().width() * scale_x
            min_rect_height = self.scroll_area.viewport().height() * scale_y
            new_width = max(new_width, min_rect_width)
            new_height = max(new_height, min_rect_height)

        # Build the new centered rectangle
        new_x = int(center_x - new_width / 2)
        new_y = int(center_y - new_height / 2)
        new_rect = QRect(new_x, new_y, int(new_width), int(new_height))

        self.set_view_rect(new_rect)

        # Set the new starting point for a possible drag
        cursor_pos = self.image.mapFromGlobal(QCursor.pos())
        self.drag_start_pos = cursor_pos

        self.layer_manager.update_display()

    def reset_view_rect(self):
        if self.pixmap:
            self.view_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
            container_size = self.scroll_area.viewport().size()
            cropped = self.pixmap.copy(self.view_rect)
            scaled = cropped.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.scaled_pixmap = scaled
            self.image.setPixmap(scaled)
            self.disattiva_zoom()

    def disattiva_zoom(self):
        self.selection_mode = False
        self.activate_selector_button.setChecked(False)
        if self.inserisci_landmarks.active or self.spezzata_plugin.active:
            self.image.setCursor(Qt.CrossCursor)

    def toggle_selection_mode(self):
        self.selection_mode = self.activate_selector_button.isChecked()
        if self.selection_mode:
            self.inserisci_landmarks.active = False
            self.spezzata_plugin.active = False
            self.image.setCursor(Qt.CrossCursor)
        else:
            self.image.setCursor(Qt.CrossCursor)

    def reset(self):
        self.landmarks = []
        self.layer_manager.update_display()

    def save_data(self):
        save_data.save_data_json(self)

    def show_working_message(self):
        QMessageBox.information(self, "Info", "Working in progress")

    def disattiva_tutti_i_plugin(self):
        self.inserisci_landmarks.deactivate()
        self.spezzata_plugin.active = False
        self.spezzata_curva.active = False
        self.image_aligner.active = False
        self.selection_mode = False
        self.activate_selector_button.setChecked(False)
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
        self.scale = None
        self.scale_unit = ""

        self.angle_deg = 0

        # Scrollbar: reset position
        self.scroll_area.horizontalScrollBar().setValue(0)
        self.scroll_area.verticalScrollBar().setValue(0)

        # Reset ComboBox
        self.landmark_combo.setCurrentIndex(0)
        self.scaling_mode.setCurrentIndex(1)

        # Buttons and states
        self.selection_mode = False
        self.activate_selector_button.setChecked(False)

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
    viewer = ImageViewer()
    # if len(sys.argv) > 1:
    #    viewer

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
