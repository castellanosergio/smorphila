"""Standalone editor for landmark, angle, and group definitions."""

from __future__ import annotations

import json
import math
import pathlib as pl
import sys
import tomllib
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
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
class GroupDefinition:
    """An ordered group of landmarks with optional segment orientations."""

    name: str
    landmarks: list[str]
    angles: list[float | None] = field(default_factory=list)


def angle_choices(step: int) -> list[int]:
    """Return all values displayed by the angle wheel."""

    if step not in {10, 20}:
        raise ValueError("Angle step must be 10 or 20 degrees")
    return list(range(-180, 181, step))


def validate_definitions(
    landmarks: dict[str, Landmark],
    groups: dict[str, GroupDefinition],
) -> list[str]:
    """Return all errors that would make the configuration invalid."""

    errors = []
    if not landmarks:
        errors.append("Define at least one landmark.")

    for landmark in landmarks.values():
        if not landmark.is_placed:
            errors.append(f"Landmark '{landmark.name}' has not been placed.")

    for group in groups.values():
        if len(group.landmarks) < 2:
            errors.append(
                f"Group '{group.name}' must contain at least two landmarks."
            )
        if len(set(group.landmarks)) != len(group.landmarks):
            errors.append(f"Group '{group.name}' contains duplicate landmarks.")
        for name in group.landmarks:
            if name not in landmarks:
                errors.append(
                    f"Group '{group.name}' references unknown landmark '{name}'."
                )
        if group.angles and len(group.angles) != len(group.landmarks) - 1:
            errors.append(
                f"Group '{group.name}' must have one angle per segment."
            )
        for angle in group.angles:
            if angle is not None and (angle < -180 or angle > 180):
                errors.append(
                    f"Group '{group.name}' contains an angle outside -180..180."
                )

    return errors


def _toml_string(value: str) -> str:
    """Encode a string using TOML-compatible JSON string escaping."""

    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_angle_array(values: list[float | None]) -> str:
    if not values or all(value is None for value in values):
        return "[]"
    serialized = [
        _toml_string("free") if value is None else f"{value:.10g}"
        for value in values
    ]
    serialized.append("0")
    return "[" + ", ".join(serialized) + "]"


def serialize_toml(
    image_path: pl.Path,
    landmarks: dict[str, Landmark],
    groups: dict[str, GroupDefinition],
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

    for group in groups.values():
        lines.extend(
            [
                "",
                f"[landmarks_groups.{_toml_string(group.name)}]",
                f"landmarks = {_toml_array(group.landmarks)}",
                f"angles = {_toml_angle_array(group.angles)}",
            ]
        )

    return "\n".join(lines) + "\n"


def _number(value, description: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{description} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{description} must be finite")
    return number


def _deserialize_angles(
    values, group_name: str, segment_count: int
) -> list[float | None]:
    if not isinstance(values, list):
        raise ValueError(f"Angles for group '{group_name}' must be an array")
    if not values:
        return []
    if len(values) == segment_count + 1:
        values = values[:-1]
    elif len(values) != segment_count:
        raise ValueError(
            f"Group '{group_name}' must have one angle per segment, "
            "plus the optional trailing value"
        )

    angles = []
    for value in values:
        if isinstance(value, str):
            if value.lower() != "free":
                raise ValueError(
                    f"Unknown angle constraint '{value}' in group '{group_name}'"
                )
            angles.append(None)
            continue
        angle = _number(value, f"Angle in group '{group_name}'")
        if angle < -180 or angle > 180:
            raise ValueError(
                f"Angle in group '{group_name}' is outside -180..180"
            )
        angles.append(angle)
    return [] if all(angle is None for angle in angles) else angles


def deserialize_toml(
    content: str,
) -> tuple[dict[str, Landmark], dict[str, GroupDefinition], list[str]]:
    """Parse a saved editor configuration without changing the GUI state."""

    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Invalid TOML: {error}") from error

    positions = data.get("landmark_positions", {})
    if not isinstance(positions, dict):
        raise ValueError("landmark_positions must be a table")
    names = data.get("landmark_names", list(positions))
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("landmark_names must be an array of strings")
    if len(set(names)) != len(names):
        raise ValueError("landmark_names contains duplicate names")

    ordered_names = names + [name for name in positions if name not in names]
    landmarks = {}
    for name in ordered_names:
        position = positions.get(name)
        if position is None:
            landmarks[name] = Landmark(name)
            continue
        if not isinstance(position, dict):
            raise ValueError(f"Position for landmark '{name}' must be a table")
        coordinates = position.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError(
                f"Coordinates for landmark '{name}' must contain two numbers"
            )
        x = _number(coordinates[0], f"X coordinate for landmark '{name}'")
        y = _number(coordinates[1], f"Y coordinate for landmark '{name}'")
        landmarks[name] = Landmark(name, x, y)

    groups_data = data.get("landmarks_groups", {})
    if not isinstance(groups_data, dict):
        raise ValueError("landmarks_groups must be a table")
    groups = {}
    for name, group_data in groups_data.items():
        if not isinstance(group_data, dict):
            raise ValueError(f"Group '{name}' must be a table")
        group_landmarks = group_data.get("landmarks")
        if not isinstance(group_landmarks, list) or not all(
            isinstance(item, str) for item in group_landmarks
        ):
            raise ValueError(f"Landmarks for group '{name}' must be strings")
        if len(group_landmarks) < 2:
            raise ValueError(f"Group '{name}' must contain at least two landmarks")
        if len(set(group_landmarks)) != len(group_landmarks):
            raise ValueError(f"Group '{name}' contains duplicate landmarks")
        unknown = [item for item in group_landmarks if item not in landmarks]
        if unknown:
            raise ValueError(
                f"Group '{name}' references unknown landmarks: {', '.join(unknown)}"
            )
        angles = _deserialize_angles(
            group_data.get("angles", []), name, len(group_landmarks) - 1
        )
        groups[name] = GroupDefinition(name, group_landmarks, angles)

    warnings = []
    if "angles" in data:
        warnings.append(
            "Legacy vertex-first angle tables were ignored because they cannot be "
            "converted to oriented segment constraints."
        )
    return landmarks, groups, warnings


class AngleWheel(QWidget):
    """Circular selector with discrete angles between -180 and 180 degrees."""

    angle_selected = Signal(int)

    def __init__(self, step: int, selected_angle: float | None = None):
        super().__init__()
        self.step = step
        self.selected_angle = selected_angle
        self.hover_angle: int | None = None
        self.setMinimumSize(620, 620)
        self.setMouseTracking(True)

    @property
    def available_angles(self) -> list[int]:
        return angle_choices(self.step)

    def _angle_at(self, position: QPointF) -> int | None:
        center = QPointF(self.width() / 2, self.height() / 2)
        dx = position.x() - center.x()
        dy = position.y() - center.y()
        distance = math.hypot(dx, dy)
        if distance < 20 or distance > min(self.width(), self.height()) / 2:
            return None
        raw_angle = math.degrees(math.atan2(dy, dx))
        snapped = round(raw_angle / self.step) * self.step
        return max(-180, min(180, snapped))

    def mouseMoveEvent(self, event: QMouseEvent):
        self.hover_angle = self._angle_at(event.position())
        self.update()

    def leaveEvent(self, event):
        self.hover_angle = None
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        angle = self._angle_at(event.position())
        if angle is None:
            return
        self.selected_angle = angle
        self.angle_selected.emit(angle)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) / 2 - 52
        painter.fillRect(self.rect(), QColor("#252525"))
        painter.setPen(QPen(QColor("#888888"), 1))
        painter.drawEllipse(center, radius, radius)

        for angle in self.available_angles:
            if angle == 180:
                continue
            radians = math.radians(angle)
            endpoint = QPointF(
                center.x() + radius * math.cos(radians),
                center.y() + radius * math.sin(radians),
            )
            is_shared_axis = angle == -180
            is_selected = self.selected_angle == angle or (
                is_shared_axis and self.selected_angle == 180
            )
            is_hovered = self.hover_angle == angle or (
                is_shared_axis and self.hover_angle == 180
            )
            color = QColor("#ffd23f") if is_selected else QColor("#62bfff")
            width = 4 if is_selected else 2 if is_hovered else 1
            painter.setPen(QPen(color, width))
            painter.drawLine(center, endpoint)

            label_radius = radius + 26
            label_point = QPointF(
                center.x() + label_radius * math.cos(radians),
                center.y() + label_radius * math.sin(radians),
            )
            label = "-180° / 180°" if angle == -180 else f"{angle}°"
            painter.setPen(QPen(QColor("#eeeeee"), 1))
            painter.drawText(
                QRectF(label_point.x() - 28, label_point.y() - 9, 56, 18),
                Qt.AlignCenter,
                label,
            )

        painter.setBrush(QColor("#eeeeee"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, 4, 4)


class RelativeAngleDiagram(AngleWheel):
    """Joint diagram for selecting a turn relative to an incoming segment."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) / 2 - 58
        painter.fillRect(self.rect(), QColor("#252525"))

        painter.setPen(QPen(QColor("#aaaaaa"), 5))
        incoming_start = QPointF(center.x() - radius, center.y())
        painter.drawLine(incoming_start, center)
        self._draw_incoming_arrow(painter, center)
        painter.setPen(QPen(QColor("#aaaaaa"), 1, Qt.DashLine))
        painter.drawLine(center, QPointF(center.x() + radius, center.y()))

        for angle in self.available_angles:
            if angle == 180:
                continue
            radians = math.radians(angle)
            endpoint = QPointF(
                center.x() + radius * math.cos(radians),
                center.y() + radius * math.sin(radians),
            )
            is_shared_axis = angle == -180
            is_selected = self.selected_angle == angle or (
                is_shared_axis and self.selected_angle == 180
            )
            is_hovered = self.hover_angle == angle or (
                is_shared_axis and self.hover_angle == 180
            )
            if is_selected:
                color = QColor("#ffd23f")
            elif angle < 0:
                color = QColor("#68b9ff")
            elif angle > 0:
                color = QColor("#ff8b68")
            else:
                color = QColor("#70d890")
            width = 5 if is_selected else 3 if is_hovered else 1
            painter.setPen(QPen(color, width))
            painter.drawLine(center, endpoint)

            label_radius = radius + 28
            label_point = QPointF(
                center.x() + label_radius * math.cos(radians),
                center.y() + label_radius * math.sin(radians),
            )
            if angle == -180:
                label = "U-turn ±180°"
            elif angle == 0:
                label = "0° straight"
            else:
                label = f"{angle:+d}°"
            painter.setPen(QPen(QColor("#eeeeee"), 1))
            painter.drawText(
                QRectF(label_point.x() - 38, label_point.y() - 9, 76, 18),
                Qt.AlignCenter,
                label,
            )

        painter.setBrush(QColor("#eeeeee"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, 5, 5)
        painter.setPen(QPen(QColor("#68b9ff"), 1))
        painter.drawText(
            QRectF(0, 5, self.width(), 24),
            Qt.AlignCenter,
            "Negative turn: counterclockwise",
        )
        painter.setPen(QPen(QColor("#ff8b68"), 1))
        painter.drawText(
            QRectF(0, self.height() - 29, self.width(), 24),
            Qt.AlignCenter,
            "Positive turn: clockwise",
        )
        painter.setPen(QPen(QColor("#dddddd"), 1))
        painter.drawText(
            QRectF(incoming_start.x() - 10, center.y() - 28, radius, 20),
            Qt.AlignCenter,
            "Incoming segment",
        )

    @staticmethod
    def _draw_incoming_arrow(painter: QPainter, vertex: QPointF):
        painter.drawLine(vertex, vertex + QPointF(-14, -9))
        painter.drawLine(vertex, vertex + QPointF(-14, 9))


class AngleSelectionDialog(QDialog):
    """Dialog for imposing or clearing one segment angle."""

    def __init__(
        self,
        segment_name: str,
        step: int,
        selected_angle: float | None,
        relative: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.selected_angle = selected_angle
        self.relative = relative
        angle_kind = "relative turn" if relative else "absolute angle"
        self.setWindowTitle(f"Set {angle_kind}: {segment_name}")
        layout = QVBoxLayout(self)
        instruction_text = (
            "The gray arrow is the incoming segment. Click an outgoing ray to "
            "set its relative turn, where 0° continues straight."
            if relative
            else "Click a compass ray to set the absolute segment orientation."
        )
        instruction = QLabel(instruction_text)
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        selector_class = RelativeAngleDiagram if relative else AngleWheel
        self.selector = selector_class(step, selected_angle)
        self.selector.angle_selected.connect(self._select_angle)
        layout.addWidget(self.selector)

        self.selection_label = QLabel()
        layout.addWidget(self.selection_label)
        clear_button = QPushButton("No constraint")
        clear_button.clicked.connect(self._clear_angle)
        layout.addWidget(clear_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_selection_label()

    def _select_angle(self, angle: int):
        self.selected_angle = float(angle)
        self._update_selection_label()

    def _clear_angle(self):
        self.selected_angle = None
        self.selector.selected_angle = None
        self.selector.update()
        self._update_selection_label()

    def _update_selection_label(self):
        text = (
            "No constraint"
            if self.selected_angle is None
            else (
                f"Selected relative turn: {self.selected_angle:g}°"
                if self.relative
                else f"Selected absolute angle: {self.selected_angle:g}°"
            )
        )
        self.selection_label.setText(text)


class ImageCanvas(QWidget):
    """Display an image and emit clicks in original-image coordinates."""

    image_clicked = Signal(QPointF)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.landmarks: dict[str, Landmark] = {}
        self.groups: dict[str, GroupDefinition] = {}
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
        self._draw_groups(painter)
        self._draw_landmarks(painter)

    def _landmark_point(self, name: str) -> QPointF | None:
        landmark = self.landmarks.get(name)
        if landmark is None or not landmark.is_placed:
            return None
        return self.image_to_widget(QPointF(landmark.x, landmark.y))

    def _draw_groups(self, painter: QPainter):
        painter.setPen(QPen(QColor(60, 180, 255, 200), 3))
        for group in self.groups.values():
            points = [self._landmark_point(name) for name in group.landmarks]
            for index, (first, second) in enumerate(zip(points, points[1:])):
                if first is not None and second is not None:
                    painter.drawLine(first, second)
                    angle = (
                        group.angles[index]
                        if index < len(group.angles)
                        else None
                    )
                    if angle is not None:
                        self._draw_arrow_head(painter, first, second)
                        midpoint = (first + second) / 2
                        painter.setPen(QPen(QColor(255, 210, 50), 1))
                        suffix = "absolute" if index == 0 else "turn"
                        painter.drawText(
                            midpoint + QPointF(6, -6), f"{angle:g}° {suffix}"
                        )
                        painter.setPen(QPen(QColor(60, 180, 255, 200), 3))

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
        self.groups: dict[str, GroupDefinition] = {}
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
        self.canvas.groups = self.groups
        self.canvas.image_clicked.connect(self._handle_canvas_click)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.addWidget(self._build_landmark_group())
        editor_layout.addWidget(self._build_angle_group())
        editor_layout.addWidget(self._build_group_section())
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
            "Select a group and impose an angle on any segment, if needed."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Angle step:"))
        self.angle_step_combo = QComboBox()
        self.angle_step_combo.addItems(["10°", "20°"])
        step_layout.addWidget(self.angle_step_combo)
        layout.addLayout(step_layout)
        buttons = QHBoxLayout()
        self.set_angle_button = QPushButton("Set angle...")
        self.clear_angle_button = QPushButton("No constraint")
        buttons.addWidget(self.set_angle_button)
        buttons.addWidget(self.clear_angle_button)
        layout.addLayout(buttons)
        self.segment_list = QListWidget()
        self.segment_list.setMinimumHeight(100)
        layout.addWidget(self.segment_list)
        self.set_angle_button.clicked.connect(self._edit_selected_segment_angle)
        self.clear_angle_button.clicked.connect(self._clear_selected_segment_angle)
        self.segment_list.itemDoubleClicked.connect(self._edit_selected_segment_angle)
        return group

    def _build_group_section(self) -> QGroupBox:
        group = QGroupBox("Groups")
        layout = QVBoxLayout(group)
        self.group_name_edit = QLineEdit()
        self.group_name_edit.setPlaceholderText("Unique group name")
        layout.addWidget(self.group_name_edit)
        buttons = QHBoxLayout()
        self.define_group_button = QPushButton("Define group")
        self.finish_group_button = QPushButton("Finish")
        self.finish_group_button.setEnabled(False)
        self.cancel_group_button = QPushButton("Cancel")
        self.delete_group_button = QPushButton("Delete selected")
        buttons.addWidget(self.define_group_button)
        buttons.addWidget(self.finish_group_button)
        buttons.addWidget(self.cancel_group_button)
        buttons.addWidget(self.delete_group_button)
        layout.addLayout(buttons)
        self.group_list = QListWidget()
        self.group_list.setMinimumHeight(100)
        layout.addWidget(self.group_list)
        self.group_list.currentRowChanged.connect(self._refresh_segments)
        self.define_group_button.clicked.connect(self._start_group)
        self.finish_group_button.clicked.connect(self._finish_group)
        self.cancel_group_button.clicked.connect(self._cancel_definition)
        self.delete_group_button.clicked.connect(self._delete_group)
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
            self.angle_step_combo,
            self.set_angle_button,
            self.clear_angle_button,
            self.segment_list,
            self.group_name_edit,
            self.define_group_button,
            self.cancel_group_button,
            self.delete_group_button,
            self.group_list,
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
        self.landmarks = {}
        self.groups = {}
        self.mode = "idle"
        self.pending_landmarks.clear()
        self.finish_group_button.setEnabled(False)
        status_message = "Image loaded. Add a landmark to begin."
        configuration_path = image_path.with_suffix(".toml")
        if configuration_path.is_file():
            try:
                content = configuration_path.read_text(encoding="utf-8")
                self.landmarks, self.groups, warnings = deserialize_toml(content)
            except (OSError, ValueError) as error:
                QMessageBox.critical(
                    self,
                    "Load TOML",
                    f"Could not load {configuration_path.name}:\n{error}",
                )
            else:
                self.output_path = configuration_path
                status_message = f"Loaded configuration from {configuration_path.name}"
                if warnings:
                    QMessageBox.warning(self, "Load TOML", "\n".join(warnings))
        self._sync_canvas_data()
        self._refresh_lists()
        self._set_editor_enabled(True)
        self.dirty = False
        self.setWindowTitle(f"{image_path.name} - SMORPHILA Landmark Definition Editor")
        self.status_bar.showMessage(status_message)

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
        for group in self.groups.values():
            group.landmarks = [
                new_name if name == old_name else name for name in group.landmarks
            ]
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
            group.name for group in self.groups.values() if name in group.landmarks
        ]
        if references:
            QMessageBox.warning(
                self,
                "Landmark",
                "Delete the following group definitions first: "
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

    def _selected_segment(self) -> tuple[GroupDefinition, int] | None:
        group_name = self._selected_group_name()
        row = self.segment_list.currentRow()
        if group_name is None or row < 0:
            QMessageBox.warning(
                self, "Oriented segments", "Select a group segment first."
            )
            return None
        return self.groups[group_name], row

    def _edit_selected_segment_angle(self, item=None):
        selection = self._selected_segment()
        if selection is None:
            return
        group, index = selection
        self._ensure_segment_angles(group)
        start = group.landmarks[index]
        end = group.landmarks[index + 1]
        step = int(self.angle_step_combo.currentText().removesuffix("°"))
        dialog = AngleSelectionDialog(
            f"{start} → {end}",
            step,
            group.angles[index],
            relative=index > 0,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        group.angles[index] = dialog.selected_angle
        self._compact_free_angles(group)
        self._refresh_segments()
        self.segment_list.setCurrentRow(index)
        self.dirty = True
        self.canvas.update()

    def _clear_selected_segment_angle(self):
        selection = self._selected_segment()
        if selection is None:
            return
        group, index = selection
        self._ensure_segment_angles(group)
        group.angles[index] = None
        self._compact_free_angles(group)
        self._refresh_segments()
        self.segment_list.setCurrentRow(index)
        self.dirty = True
        self.canvas.update()

    @staticmethod
    def _ensure_segment_angles(group: GroupDefinition):
        segment_count = len(group.landmarks) - 1
        if not group.angles:
            group.angles = [None] * segment_count

    @staticmethod
    def _compact_free_angles(group: GroupDefinition):
        if group.angles and all(angle is None for angle in group.angles):
            group.angles.clear()

    def _start_group(self):
        name = self._clean_name(self.group_name_edit, "Group", self.groups)
        if name is None:
            return
        if len([item for item in self.landmarks.values() if item.is_placed]) < 2:
            QMessageBox.warning(self, "Group", "Place at least two landmarks first.")
            return
        self.mode = "group"
        self.pending_name = name
        self.pending_landmarks = []
        self.finish_group_button.setEnabled(True)
        self.status_bar.showMessage(
            "Select group landmarks in order, then click Finish."
        )

    def _cancel_definition(self):
        if self.mode != "group":
            return
        self.mode = "idle"
        self.pending_name = ""
        self.pending_landmarks.clear()
        self.finish_group_button.setEnabled(False)
        self.status_bar.showMessage("Definition cancelled.")

    def _finish_group(self):
        if self.mode != "group":
            return
        if len(self.pending_landmarks) < 2:
            QMessageBox.warning(self, "Group", "Select at least two landmarks.")
            return
        self.groups[self.pending_name] = GroupDefinition(
            self.pending_name, self.pending_landmarks.copy()
        )
        self.group_name_edit.clear()
        self.mode = "idle"
        self.pending_landmarks.clear()
        self.finish_group_button.setEnabled(False)
        self._refresh_groups()
        self._select_group_by_name(self.pending_name)
        self._refresh_segments()
        self.dirty = True
        self.canvas.update()
        self.status_bar.showMessage("Group created.")

    def _delete_group(self):
        row = self.group_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Group", "Select a group first.")
            return
        name = self.group_list.item(row).data(Qt.UserRole)
        del self.groups[name]
        self._refresh_groups()
        self._refresh_segments()
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
            self._refresh_landmarks()
            self._select_landmark_by_name(name)
            self.status_bar.showMessage(f"Landmark '{name}' placed.")
            self.canvas.update()
            return

        if self.mode != "group":
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

    def _refresh_segments(self, row=None):
        selected_row = self.segment_list.currentRow()
        self.segment_list.clear()
        group_name = self._selected_group_name()
        if group_name is None:
            return
        group = self.groups[group_name]
        for index, (start, end) in enumerate(
            zip(group.landmarks, group.landmarks[1:])
        ):
            angle = group.angles[index] if index < len(group.angles) else None
            if angle is None:
                constraint = "free"
            elif index == 0:
                constraint = f"{angle:g}° absolute"
            else:
                constraint = f"{angle:+g}° turn"
            self.segment_list.addItem(f"{start} → {end}: {constraint}")
        if self.segment_list.count():
            selected_row = max(
                0, min(selected_row, self.segment_list.count() - 1)
            )
            self.segment_list.setCurrentRow(selected_row)

    def _selected_group_name(self) -> str | None:
        item = self.group_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _select_group_by_name(self, name: str):
        for row in range(self.group_list.count()):
            if self.group_list.item(row).data(Qt.UserRole) == name:
                self.group_list.setCurrentRow(row)
                return

    def _refresh_groups(self):
        selected_name = self._selected_group_name()
        self.group_list.clear()
        for group in self.groups.values():
            self.group_list.addItem(
                f"{group.name}: {' - '.join(group.landmarks)}"
            )
            self.group_list.item(self.group_list.count() - 1).setData(
                Qt.UserRole, group.name
            )
        if selected_name:
            self._select_group_by_name(selected_name)

    def _refresh_lists(self):
        self._refresh_landmarks()
        self._refresh_groups()
        self._refresh_segments()
        self.canvas.update()

    def _sync_canvas_data(self):
        self.canvas.landmarks = self.landmarks
        self.canvas.groups = self.groups

    def save_toml(self):
        if self.image_path is None:
            QMessageBox.warning(self, "Save TOML", "Open an image first.")
            return
        errors = validate_definitions(self.landmarks, self.groups)
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
                    self.image_path, self.landmarks, self.groups
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
