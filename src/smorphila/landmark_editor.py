"""Standalone editor for landmark, angle, and skeleton definitions."""

from __future__ import annotations

import json
import math
import pathlib as pl
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCloseEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

IMAGE_FILTER = "Images (*.jpg *.JPG *.jpeg *.JPEG *.png *.PNG);;All files (*)"


@dataclass
class Landmark:
    """A named point in original-image coordinates."""

    name: str
    x: float | None = None
    y: float | None = None

    @property
    def is_placed(self) -> bool:
        return self.x is not None and self.y is not None


@dataclass
class SkeletonDefinition:
    """An ordered group of landmarks with optional segment orientations."""

    name: str
    landmarks: list[str]
    angles: list[float] = field(default_factory=list)


def _normalize_angle(angle: float) -> float:
    """Normalize an angle to (-180, 180], preserving left as 180 degrees."""

    normalized = (angle + 180) % 360 - 180
    return 180.0 if math.isclose(normalized, -180.0) else normalized


def segment_orientation(start: QPointF, end: QPointF) -> float:
    """Return the oriented segment angle in Qt image coordinates."""

    dx = end.x() - start.x()
    dy = end.y() - start.y()
    if dx == 0 and dy == 0:
        raise ValueError("Oriented segments must have different endpoints")
    return _normalize_angle(math.degrees(math.atan2(dy, dx)))


def calculate_oriented_angles(points: list[QPointF]) -> list[float]:
    """Build the angle list consumed by ArtiPlugin from ordered points."""

    if len(points) < 2:
        raise ValueError("At least two points are required")
    orientations = [
        segment_orientation(start, end) for start, end in zip(points, points[1:])
    ]
    turns = [
        _normalize_angle(current - previous)
        for previous, current in zip(orientations, orientations[1:])
    ]
    return [orientations[0], *turns, 0.0]


def validate_definitions(
    landmarks: dict[str, Landmark],
    skeletons: dict[str, SkeletonDefinition],
) -> list[str]:
    """Return all errors that would make the configuration invalid."""

    errors = []
    if not landmarks:
        errors.append("Define at least one landmark.")

    for landmark in landmarks.values():
        if not landmark.is_placed:
            errors.append(f"Landmark '{landmark.name}' has not been placed.")

    for skeleton in skeletons.values():
        if len(skeleton.landmarks) < 2:
            errors.append(
                f"Skeleton '{skeleton.name}' must contain at least two landmarks."
            )
        if len(set(skeleton.landmarks)) != len(skeleton.landmarks):
            errors.append(f"Skeleton '{skeleton.name}' contains duplicate landmarks.")
        skeleton_points = []
        for name in skeleton.landmarks:
            if name not in landmarks:
                errors.append(
                    f"Skeleton '{skeleton.name}' references unknown landmark '{name}'."
                )
            elif landmarks[name].is_placed:
                skeleton_points.append(QPointF(landmarks[name].x, landmarks[name].y))
        if skeleton.angles and len(skeleton.angles) != len(skeleton.landmarks):
            errors.append(
                f"Skeleton '{skeleton.name}' must have one angle per landmark."
            )
        if skeleton.angles and len(skeleton_points) == len(skeleton.landmarks):
            try:
                calculate_oriented_angles(skeleton_points)
            except ValueError as error:
                errors.append(f"Skeleton '{skeleton.name}' is invalid: {error}.")

    return errors


def _toml_string(value: str) -> str:
    """Encode a string using TOML-compatible JSON string escaping."""

    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_number_array(values: list[float]) -> str:
    return "[" + ", ".join(f"{value:.10g}" for value in values) + "]"


def serialize_toml(
    image_path: pl.Path,
    landmarks: dict[str, Landmark],
    skeletons: dict[str, SkeletonDefinition],
) -> str:
    """Serialize editor data without requiring an additional TOML package."""

    lines = [
        f"source_image = {_toml_string(str(image_path))}",
        f"landmark_names = {_toml_array(list(landmarks))}",
    ]

    for landmark in landmarks.values():
        lines.extend(
            [
                "",
                f"[landmark_positions.{_toml_string(landmark.name)}]",
                f"coordinates = [{landmark.x:.10g}, {landmark.y:.10g}]",
            ]
        )

    for skeleton in skeletons.values():
        lines.extend(
            [
                "",
                f"[landmarks_groups.{_toml_string(skeleton.name)}]",
                f"landmarks = {_toml_array(skeleton.landmarks)}",
                f"angles = {_toml_number_array(skeleton.angles)}",
            ]
        )

    return "\n".join(lines) + "\n"


class ImageCanvas(QWidget):
    """Display an image and emit clicks in original-image coordinates."""

    image_clicked = Signal(QPointF)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.landmarks: dict[str, Landmark] = {}
        self.skeletons: dict[str, SkeletonDefinition] = {}
        self.selected_landmark = ""
        self.setMinimumSize(500, 400)
        self.setCursor(Qt.CrossCursor)

    def set_image(self, image_path: pl.Path) -> bool:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return False
        self.pixmap = pixmap
        self.update()
        return True

    def image_rect(self) -> QRectF:
        if self.pixmap.isNull():
            return QRectF()
        scale = min(
            self.width() / self.pixmap.width(), self.height() / self.pixmap.height()
        )
        width = self.pixmap.width() * scale
        height = self.pixmap.height() * scale
        return QRectF(
            (self.width() - width) / 2,
            (self.height() - height) / 2,
            width,
            height,
        )

    def image_to_widget(self, point: QPointF) -> QPointF:
        rect = self.image_rect()
        return QPointF(
            rect.left() + point.x() * rect.width() / self.pixmap.width(),
            rect.top() + point.y() * rect.height() / self.pixmap.height(),
        )

    def widget_to_image(self, point: QPointF) -> QPointF | None:
        rect = self.image_rect()
        if rect.isEmpty() or not rect.contains(point):
            return None
        return QPointF(
            (point.x() - rect.left()) * self.pixmap.width() / rect.width(),
            (point.y() - rect.top()) * self.pixmap.height() / rect.height(),
        )

    def closest_landmark(
        self, point: QPointF, maximum_distance: float = 18
    ) -> str | None:
        closest_name = None
        closest_distance = maximum_distance
        for landmark in self.landmarks.values():
            if not landmark.is_placed:
                continue
            widget_point = self.image_to_widget(QPointF(landmark.x, landmark.y))
            distance = math.hypot(
                point.x() - widget_point.x(), point.y() - widget_point.y()
            )
            if distance <= closest_distance:
                closest_name = landmark.name
                closest_distance = distance
        return closest_name

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton or self.pixmap.isNull():
            return
        image_point = self.widget_to_image(event.position())
        if image_point is not None:
            self.image_clicked.emit(image_point)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#252525"))
        if self.pixmap.isNull():
            painter.setPen(QColor("#dddddd"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Open an image to begin")
            return

        painter.setRenderHint(QPainter.Antialiasing)
        target = self.image_rect()
        painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        self._draw_skeletons(painter)
        self._draw_landmarks(painter)

    def _landmark_point(self, name: str) -> QPointF | None:
        landmark = self.landmarks.get(name)
        if landmark is None or not landmark.is_placed:
            return None
        return self.image_to_widget(QPointF(landmark.x, landmark.y))

    def _draw_skeletons(self, painter: QPainter):
        painter.setPen(QPen(QColor(60, 180, 255, 200), 3))
        for skeleton in self.skeletons.values():
            points = [self._landmark_point(name) for name in skeleton.landmarks]
            for first, second in zip(points, points[1:]):
                if first is not None and second is not None:
                    painter.drawLine(first, second)
                    if skeleton.angles:
                        self._draw_arrow_head(painter, first, second)

    def _draw_arrow_head(self, painter: QPainter, start: QPointF, end: QPointF):
        direction = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_length = 12
        for offset in (-2.6, 2.6):
            arrow_end = QPointF(
                end.x() + arrow_length * math.cos(direction + offset),
                end.y() + arrow_length * math.sin(direction + offset),
            )
            painter.drawLine(end, arrow_end)

    def _draw_landmarks(self, painter: QPainter):
        for landmark in self.landmarks.values():
            if not landmark.is_placed:
                continue
            point = self.image_to_widget(QPointF(landmark.x, landmark.y))
            color = (
                QColor("#42d66b")
                if landmark.name == self.selected_landmark
                else QColor("#ff4545")
            )
            painter.setPen(QPen(Qt.black, 1))
            painter.setBrush(color)
            painter.drawEllipse(point, 6, 6)
            painter.setPen(QPen(Qt.white, 1))
            painter.drawText(point + QPointF(8, -8), landmark.name)


class LandmarkEditor(QMainWindow):
    """Main window for creating landmark configuration files."""

    def __init__(self):
        super().__init__()
        self.image_path: pl.Path | None = None
        self.output_path: pl.Path | None = None
        self.landmarks: dict[str, Landmark] = {}
        self.skeletons: dict[str, SkeletonDefinition] = {}
        self.mode = "idle"
        self.pending_name = ""
        self.pending_landmarks: list[str] = []
        self.dirty = False

        self.setWindowTitle("SMORPHILA Landmark Definition Editor")
        self.resize(1200, 760)
        self._build_interface()
        self._build_menu()
        self._set_editor_enabled(False)

    def _build_interface(self):
        self.canvas = ImageCanvas()
        self.canvas.landmarks = self.landmarks
        self.canvas.skeletons = self.skeletons
        self.canvas.image_clicked.connect(self._handle_canvas_click)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.addWidget(self._build_landmark_group())
        editor_layout.addWidget(self._build_angle_group())
        editor_layout.addWidget(self._build_skeleton_group())
        editor_layout.addStretch()
        editor_panel.setMinimumWidth(340)

        splitter = QSplitter()
        splitter.addWidget(self.canvas)
        splitter.addWidget(editor_panel)
        splitter.setStretchFactor(0, 1)
        self.setCentralWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Open an image to begin")

    def _build_landmark_group(self) -> QGroupBox:
        group = QGroupBox("Landmarks")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        self.landmark_name_edit = QLineEdit()
        self.landmark_name_edit.setPlaceholderText("Unique landmark name")
        form.addRow("Name:", self.landmark_name_edit)
        layout.addLayout(form)

        self.add_landmark_button = QPushButton("Add landmark")
        self.place_landmark_button = QPushButton("Place selected")
        self.rename_landmark_button = QPushButton("Rename selected")
        self.delete_landmark_button = QPushButton("Delete selected")
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_landmark_button)
        buttons.addWidget(self.place_landmark_button)
        layout.addLayout(buttons)
        buttons = QHBoxLayout()
        buttons.addWidget(self.rename_landmark_button)
        buttons.addWidget(self.delete_landmark_button)
        layout.addLayout(buttons)

        self.landmark_list = QListWidget()
        self.landmark_list.setMinimumHeight(130)
        layout.addWidget(self.landmark_list)
        self.add_landmark_button.clicked.connect(self._add_landmark)
        self.place_landmark_button.clicked.connect(self._place_selected_landmark)
        self.rename_landmark_button.clicked.connect(self._rename_landmark)
        self.delete_landmark_button.clicked.connect(self._delete_landmark)
        self.landmark_list.currentRowChanged.connect(self._select_landmark)
        return group

    def _build_angle_group(self) -> QGroupBox:
        group = QGroupBox("Oriented segments")
        layout = QVBoxLayout(group)
        description = QLabel(
            "Select a skeleton, then calculate its segment orientations."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = QHBoxLayout()
        self.define_angles_button = QPushButton("Calculate angles")
        self.clear_angles_button = QPushButton("Clear angles")
        buttons.addWidget(self.define_angles_button)
        buttons.addWidget(self.clear_angles_button)
        layout.addLayout(buttons)
        self.angle_list = QListWidget()
        self.angle_list.setMinimumHeight(100)
        layout.addWidget(self.angle_list)
        self.define_angles_button.clicked.connect(self._calculate_selected_angles)
        self.clear_angles_button.clicked.connect(self._clear_selected_angles)
        self.angle_list.currentRowChanged.connect(self._select_angle_skeleton)
        return group

    def _build_skeleton_group(self) -> QGroupBox:
        group = QGroupBox("Skeletons")
        layout = QVBoxLayout(group)
        self.skeleton_name_edit = QLineEdit()
        self.skeleton_name_edit.setPlaceholderText("Unique skeleton name")
        layout.addWidget(self.skeleton_name_edit)
        buttons = QHBoxLayout()
        self.define_skeleton_button = QPushButton("Define skeleton")
        self.finish_skeleton_button = QPushButton("Finish")
        self.finish_skeleton_button.setEnabled(False)
        self.cancel_skeleton_button = QPushButton("Cancel")
        self.delete_skeleton_button = QPushButton("Delete selected")
        buttons.addWidget(self.define_skeleton_button)
        buttons.addWidget(self.finish_skeleton_button)
        buttons.addWidget(self.cancel_skeleton_button)
        buttons.addWidget(self.delete_skeleton_button)
        layout.addLayout(buttons)
        self.skeleton_list = QListWidget()
        self.skeleton_list.setMinimumHeight(100)
        layout.addWidget(self.skeleton_list)
        self.define_skeleton_button.clicked.connect(self._start_skeleton)
        self.finish_skeleton_button.clicked.connect(self._finish_skeleton)
        self.cancel_skeleton_button.clicked.connect(self._cancel_definition)
        self.delete_skeleton_button.clicked.connect(self._delete_skeleton)
        return group

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open image...", self)
        save_action = QAction("Save TOML...", self)
        exit_action = QAction("Exit", self)
        open_action.setShortcut("Ctrl+O")
        save_action.setShortcut("Ctrl+S")
        open_action.triggered.connect(self.open_image)
        save_action.triggered.connect(self.save_toml)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)
        self.save_action = save_action
        self.save_action.setEnabled(False)

    def _set_editor_enabled(self, enabled: bool):
        for widget in (
            self.landmark_name_edit,
            self.add_landmark_button,
            self.place_landmark_button,
            self.rename_landmark_button,
            self.delete_landmark_button,
            self.landmark_list,
            self.define_angles_button,
            self.clear_angles_button,
            self.angle_list,
            self.skeleton_name_edit,
            self.define_skeleton_button,
            self.cancel_skeleton_button,
            self.delete_skeleton_button,
            self.skeleton_list,
        ):
            widget.setEnabled(enabled)
        self.save_action.setEnabled(enabled)

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "Discard the unsaved changes?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def open_image(self):
        if not self._confirm_discard():
            return
        file_name, _ = QFileDialog.getOpenFileName(self, "Open image", "", IMAGE_FILTER)
        if not file_name:
            return
        image_path = pl.Path(file_name)
        if not self.canvas.set_image(image_path):
            QMessageBox.critical(
                self, "Open image", "The selected image could not be loaded."
            )
            return

        self.image_path = image_path
        self.output_path = None
        self.landmarks.clear()
        self.skeletons.clear()
        self.mode = "idle"
        self.pending_landmarks.clear()
        self.finish_skeleton_button.setEnabled(False)
        self._refresh_lists()
        self._set_editor_enabled(True)
        self.dirty = False
        self.setWindowTitle(f"{image_path.name} - SMORPHILA Landmark Definition Editor")
        self.status_bar.showMessage("Image loaded. Add a landmark to begin.")

    def _clean_name(self, edit: QLineEdit, kind: str, collection: dict) -> str | None:
        name = edit.text().strip()
        if not name:
            QMessageBox.warning(self, kind, f"Enter a {kind.lower()} name.")
            return None
        if name in collection:
            QMessageBox.warning(self, kind, f"The name '{name}' is already in use.")
            return None
        return name

    def _add_landmark(self):
        name = self._clean_name(self.landmark_name_edit, "Landmark", self.landmarks)
        if name is None:
            return
        self.landmarks[name] = Landmark(name)
        self.landmark_name_edit.clear()
        self._refresh_landmarks()
        self.landmark_list.setCurrentRow(len(self.landmarks) - 1)
        self.mode = "place"
        self.dirty = True
        self.status_bar.showMessage(f"Click the image to place landmark '{name}'.")

    def _selected_landmark_name(self) -> str | None:
        item = self.landmark_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _place_selected_landmark(self):
        name = self._selected_landmark_name()
        if name is None:
            QMessageBox.warning(self, "Landmark", "Select a landmark first.")
            return
        self.mode = "place"
        self.status_bar.showMessage(f"Click the image to place landmark '{name}'.")

    def _rename_landmark(self):
        old_name = self._selected_landmark_name()
        if old_name is None:
            QMessageBox.warning(self, "Landmark", "Select a landmark first.")
            return
        new_name = self.landmark_name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(
                self, "Landmark", "Enter the new name in the Name field."
            )
            return
        if new_name != old_name and new_name in self.landmarks:
            QMessageBox.warning(
                self, "Landmark", f"The name '{new_name}' is already in use."
            )
            return

        renamed_landmarks = {}
        for name, landmark in self.landmarks.items():
            if name == old_name:
                landmark.name = new_name
                renamed_landmarks[new_name] = landmark
            else:
                renamed_landmarks[name] = landmark
        self.landmarks = renamed_landmarks
        for skeleton in self.skeletons.values():
            skeleton.landmarks = [
                new_name if name == old_name else name for name in skeleton.landmarks
            ]
        self._recalculate_skeleton_angles()
        self._sync_canvas_data()
        self.landmark_name_edit.clear()
        self._refresh_lists()
        self._select_landmark_by_name(new_name)
        self.dirty = True

    def _delete_landmark(self):
        name = self._selected_landmark_name()
        if name is None:
            QMessageBox.warning(self, "Landmark", "Select a landmark first.")
            return
        references = [
            skeleton.name
            for skeleton in self.skeletons.values()
            if name in skeleton.landmarks
        ]
        if references:
            QMessageBox.warning(
                self,
                "Landmark",
                "Delete the following skeleton definitions first: "
                + ", ".join(references),
            )
            return
        del self.landmarks[name]
        self._refresh_landmarks()
        self.dirty = True
        self.canvas.update()

    def _select_landmark(self):
        self.canvas.selected_landmark = self._selected_landmark_name() or ""
        self.canvas.update()

    def _select_landmark_by_name(self, name: str):
        for row in range(self.landmark_list.count()):
            if self.landmark_list.item(row).data(Qt.UserRole) == name:
                self.landmark_list.setCurrentRow(row)
                return

    def _calculate_selected_angles(self):
        name = self._selected_skeleton_name()
        if name is None:
            QMessageBox.warning(
                self, "Oriented segments", "Select a skeleton first."
            )
            return
        skeleton = self.skeletons[name]
        points = [
            QPointF(self.landmarks[item].x, self.landmarks[item].y)
            for item in skeleton.landmarks
        ]
        try:
            skeleton.angles = calculate_oriented_angles(points)
        except ValueError as error:
            QMessageBox.warning(self, "Oriented segments", str(error))
            return
        self._refresh_angles()
        self._select_angle_by_name(name)
        self.dirty = True
        self.canvas.update()
        self.status_bar.showMessage(f"Angles calculated for skeleton '{name}'.")

    def _clear_selected_angles(self):
        name = self._selected_skeleton_name()
        if name is None or name not in self.skeletons:
            QMessageBox.warning(
                self, "Oriented segments", "Select a skeleton first."
            )
            return
        self.skeletons[name].angles.clear()
        self._refresh_angles()
        self.dirty = True
        self.canvas.update()
        self.status_bar.showMessage(f"Angles cleared for skeleton '{name}'.")

    def _start_skeleton(self):
        name = self._clean_name(self.skeleton_name_edit, "Skeleton", self.skeletons)
        if name is None:
            return
        if len([item for item in self.landmarks.values() if item.is_placed]) < 2:
            QMessageBox.warning(self, "Skeleton", "Place at least two landmarks first.")
            return
        self.mode = "skeleton"
        self.pending_name = name
        self.pending_landmarks = []
        self.finish_skeleton_button.setEnabled(True)
        self.status_bar.showMessage(
            "Select skeleton landmarks in order, then click Finish."
        )

    def _cancel_definition(self):
        if self.mode != "skeleton":
            return
        self.mode = "idle"
        self.pending_name = ""
        self.pending_landmarks.clear()
        self.finish_skeleton_button.setEnabled(False)
        self.status_bar.showMessage("Definition cancelled.")

    def _finish_skeleton(self):
        if self.mode != "skeleton":
            return
        if len(self.pending_landmarks) < 2:
            QMessageBox.warning(self, "Skeleton", "Select at least two landmarks.")
            return
        self.skeletons[self.pending_name] = SkeletonDefinition(
            self.pending_name, self.pending_landmarks.copy()
        )
        self.skeleton_name_edit.clear()
        self.mode = "idle"
        self.pending_landmarks.clear()
        self.finish_skeleton_button.setEnabled(False)
        self._refresh_skeletons()
        self.dirty = True
        self.canvas.update()
        self.status_bar.showMessage("Skeleton created.")

    def _delete_skeleton(self):
        row = self.skeleton_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Skeleton", "Select a skeleton first.")
            return
        name = self.skeleton_list.item(row).data(Qt.UserRole)
        del self.skeletons[name]
        self._refresh_skeletons()
        self._refresh_angles()
        self.dirty = True
        self.canvas.update()

    def _handle_canvas_click(self, image_point: QPointF):
        if self.mode == "place":
            name = self._selected_landmark_name()
            if name is None:
                return
            landmark = self.landmarks[name]
            landmark.x = image_point.x()
            landmark.y = image_point.y()
            self.mode = "idle"
            self.dirty = True
            self._recalculate_skeleton_angles()
            self._refresh_landmarks()
            self._refresh_angles()
            self._select_landmark_by_name(name)
            self.status_bar.showMessage(f"Landmark '{name}' placed.")
            self.canvas.update()
            return

        if self.mode != "skeleton":
            return
        widget_point = self.canvas.image_to_widget(image_point)
        name = self.canvas.closest_landmark(widget_point)
        if name is None:
            self.status_bar.showMessage("Click closer to a placed landmark.")
            return
        if name in self.pending_landmarks:
            self.status_bar.showMessage("Each landmark can only be selected once.")
            return
        self.pending_landmarks.append(name)

        self.status_bar.showMessage(
            f"Added '{name}'. Select another landmark or click Finish."
        )

    def _refresh_landmarks(self):
        selected_name = self._selected_landmark_name()
        self.landmark_list.clear()
        for landmark in self.landmarks.values():
            state = "placed" if landmark.is_placed else "not placed"
            self.landmark_list.addItem(f"{landmark.name} ({state})")
            self.landmark_list.item(self.landmark_list.count() - 1).setData(
                Qt.UserRole, landmark.name
            )
        if selected_name:
            self._select_landmark_by_name(selected_name)
        self.canvas.update()

    def _refresh_angles(self):
        self.angle_list.clear()
        for skeleton in self.skeletons.values():
            if not skeleton.angles:
                continue
            segment_values = [
                (
                    f"{skeleton.landmarks[0]} → {skeleton.landmarks[1]}: "
                    f"{skeleton.angles[0]:.2f}° absolute"
                )
            ]
            for index in range(1, len(skeleton.landmarks) - 1):
                segment_values.append(
                    f"{skeleton.landmarks[index]} → "
                    f"{skeleton.landmarks[index + 1]}: "
                    f"{skeleton.angles[index]:+.2f}° turn"
                )
            item_text = f"{skeleton.name}: " + "; ".join(segment_values)
            self.angle_list.addItem(item_text)
            self.angle_list.item(self.angle_list.count() - 1).setData(
                Qt.UserRole, skeleton.name
            )

    def _recalculate_skeleton_angles(self):
        for skeleton in self.skeletons.values():
            if not skeleton.angles:
                continue
            points = [
                QPointF(self.landmarks[name].x, self.landmarks[name].y)
                for name in skeleton.landmarks
            ]
            try:
                skeleton.angles = calculate_oriented_angles(points)
            except ValueError:
                skeleton.angles = [math.nan] * len(skeleton.landmarks)

    def _selected_skeleton_name(self) -> str | None:
        item = self.skeleton_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _select_angle_skeleton(self):
        item = self.angle_list.currentItem()
        if item:
            self._select_skeleton_by_name(item.data(Qt.UserRole))

    def _select_skeleton_by_name(self, name: str):
        for row in range(self.skeleton_list.count()):
            if self.skeleton_list.item(row).data(Qt.UserRole) == name:
                self.skeleton_list.setCurrentRow(row)
                return

    def _select_angle_by_name(self, name: str):
        for row in range(self.angle_list.count()):
            if self.angle_list.item(row).data(Qt.UserRole) == name:
                self.angle_list.setCurrentRow(row)
                return

    def _refresh_skeletons(self):
        selected_name = self._selected_skeleton_name()
        self.skeleton_list.clear()
        for skeleton in self.skeletons.values():
            self.skeleton_list.addItem(
                f"{skeleton.name}: {' - '.join(skeleton.landmarks)}"
            )
            self.skeleton_list.item(self.skeleton_list.count() - 1).setData(
                Qt.UserRole, skeleton.name
            )
        if selected_name:
            self._select_skeleton_by_name(selected_name)

    def _refresh_lists(self):
        self._refresh_landmarks()
        self._refresh_angles()
        self._refresh_skeletons()
        self.canvas.update()

    def _sync_canvas_data(self):
        self.canvas.landmarks = self.landmarks
        self.canvas.skeletons = self.skeletons

    def save_toml(self):
        if self.image_path is None:
            QMessageBox.warning(self, "Save TOML", "Open an image first.")
            return
        errors = validate_definitions(self.landmarks, self.skeletons)
        if errors:
            QMessageBox.warning(self, "Save TOML", "\n".join(errors))
            return

        suggested_path = self.output_path or self.image_path.with_suffix(".toml")
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save landmark definitions",
            str(suggested_path),
            "TOML files (*.toml)",
        )
        if not file_name:
            return
        output_path = pl.Path(file_name)
        if output_path.suffix.lower() != ".toml":
            output_path = output_path.with_suffix(".toml")
        try:
            output_path.write_text(
                serialize_toml(
                    self.image_path, self.landmarks, self.skeletons
                ),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.critical(self, "Save TOML", str(error))
            return

        self.output_path = output_path
        self.dirty = False
        self.status_bar.showMessage(f"Saved {output_path}")

    def closeEvent(self, event: QCloseEvent):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


def run():
    app = QApplication(sys.argv)
    editor = LandmarkEditor()
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
