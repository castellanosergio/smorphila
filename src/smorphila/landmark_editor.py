"""Standalone editor for landmark, angle, and group definitions."""

from __future__ import annotations

import json
import math
import os
import pathlib as pl
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
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
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

try:
    from .project_store import load_project, save_project
except ImportError:
    from project_store import load_project, save_project

IMAGE_FILTER = "Images (*.jpg *.JPG *.jpeg *.JPEG *.png *.PNG);;All files (*)"
ANGLE_SELECTION_STEP = 10


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
class CurveDefinition:
    """A curve defined by two anchor landmarks and a point count."""

    name: str
    point_count: int
    start_landmark: str
    end_landmark: str


@dataclass
class GroupDefinition:
    """A group represented by an ordered list of oriented segments."""

    name: str
    segments: list[tuple[str, str]]
    angles: list[float | None] = field(default_factory=list)
    reference_points: dict[str, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self):
        # Accept the former landmark-chain constructor while reading old data.
        if self.segments and isinstance(self.segments[0], str):
            names = self.segments  # type: ignore[assignment]
            self.segments = list(zip(names, names[1:]))


@dataclass
class MainAxisDefinition:
    """A reference axis defined by landmark names and its target angle."""

    start_landmark: str
    end_landmark: str
    angle_from_vertical: float = 0


def axis_landmark_points(
    axis: MainAxisDefinition, landmarks: dict[str, Landmark]
) -> tuple[QPointF, QPointF] | None:
    """Return the current points for a reference axis when both anchors are placed."""

    start = landmarks.get(axis.start_landmark)
    end = landmarks.get(axis.end_landmark)
    if start is None or end is None or not start.is_placed or not end.is_placed:
        return None
    return QPointF(start.x, start.y), QPointF(end.x, end.y)


def normalize_rotation(angle: float) -> float:
    """Normalize a rotation to (-180, 180]."""

    normalized = (angle + 180) % 360 - 180
    return 180.0 if math.isclose(normalized, -180.0) else normalized


def proposed_axis_rotation(
    axis: MainAxisDefinition,
    landmarks: dict[str, Landmark],
    current_rotation: float = 0,
) -> float:
    """Return the rotation needed to align the displayed reference axis."""

    points = axis_landmark_points(axis, landmarks)
    if points is None or points[0] == points[1]:
        raise ValueError("The reference axis points must be distinct")
    current_heading = trigonometric_heading(*points) - current_rotation
    target_heading = 90 + axis.angle_from_vertical
    return normalize_rotation(current_heading - target_heading)


def trigonometric_heading(start: QPointF, end: QPointF) -> float:
    """Return a screen-image vector heading with positive angles counterclockwise."""

    return normalize_rotation(
        math.degrees(math.atan2(-(end.y() - start.y()), end.x() - start.x()))
    )


def angle_from_axis(
    start: QPointF,
    end: QPointF,
    axis: MainAxisDefinition | None,
    landmarks: dict[str, Landmark],
) -> float:
    """Return a segment angle relative to the oriented reference axis."""

    segment_heading = trigonometric_heading(start, end)
    axis_points = axis_landmark_points(axis, landmarks) if axis else None
    axis_heading = trigonometric_heading(*axis_points) if axis_points else 90.0
    return normalize_rotation(segment_heading - axis_heading)


def angle_choices(step: int) -> list[int]:
    """Return all values displayed by the angle wheel."""

    if step not in {10, 20}:
        raise ValueError("Angle step must be 10 or 20 degrees")
    return list(range(-180, 181, step))


def validate_definitions(
    landmarks: dict[str, Landmark],
    groups: dict[str, GroupDefinition],
    curves: dict[str, CurveDefinition] | None = None,
    main_axis: MainAxisDefinition | None = None,
    distances: dict[str, tuple[str, str]] | None = None,
) -> list[str]:
    """Return all errors that would make the configuration invalid."""

    errors = []
    if not landmarks:
        errors.append("Define at least one landmark.")

    for landmark in landmarks.values():
        if not landmark.is_placed:
            errors.append(f"Landmark '{landmark.name}' has not been placed.")

    for group in groups.values():
        if not group.segments:
            errors.append(f"Group '{group.name}' must contain at least one segment.")
        for start, end in group.segments:
            if start == end:
                errors.append(f"Group '{group.name}' contains a zero-length segment.")
            for name in (start, end):
                if name not in landmarks:
                    errors.append(
                        f"Group '{group.name}' references unknown landmark '{name}'."
                    )
        if group.angles and len(group.angles) != len(group.segments):
            errors.append(f"Group '{group.name}' must have one angle per segment.")
        for angle in group.angles:
            if angle is not None and (angle < -180 or angle > 180):
                errors.append(
                    f"Group '{group.name}' contains an angle outside -180..180."
                )

    for curve in (curves or {}).values():
        if (
            isinstance(curve.point_count, bool)
            or not isinstance(curve.point_count, int)
            or curve.point_count < 2
        ):
            errors.append(f"Curve '{curve.name}' must contain at least two points.")
        if curve.start_landmark == curve.end_landmark:
            errors.append(f"Curve '{curve.name}' must use two different anchors.")
        for landmark_name in (curve.start_landmark, curve.end_landmark):
            if landmark_name not in landmarks:
                errors.append(
                    f"Curve '{curve.name}' references unknown landmark "
                    f"'{landmark_name}'."
                )

    for distance_name, landmark_pair in (distances or {}).items():
        if len(landmark_pair) != 2 or landmark_pair[0] == landmark_pair[1]:
            errors.append(f"Distance '{distance_name}' must use two different landmarks.")
            continue
        for landmark_name in landmark_pair:
            if landmark_name not in landmarks:
                errors.append(
                    f"Distance '{distance_name}' references unknown landmark "
                    f"'{landmark_name}'."
                )

    if main_axis is not None:
        if main_axis.start_landmark == main_axis.end_landmark:
            errors.append("The reference axis must use two different landmarks.")
        for landmark_name in (
            main_axis.start_landmark,
            main_axis.end_landmark,
        ):
            if landmark_name not in landmarks:
                errors.append(
                    f"The reference axis references unknown landmark '{landmark_name}'."
                )
        if main_axis.angle_from_vertical < -180 or main_axis.angle_from_vertical > 180:
            errors.append("The reference axis angle must be within -180..180.")

    return errors


def serialize_json(
    image_path: pl.Path,
    landmarks: dict[str, Landmark],
    groups: dict[str, GroupDefinition],
    main_axis: MainAxisDefinition | None = None,
    curves: dict[str, CurveDefinition] | None = None,
    image_rotation: float = 0,
    json_path: pl.Path | None = None,
    distances: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Serialize the complete project definition as JSON."""

    source_image = str(image_path)
    if json_path is not None:
        source_image = pl.Path(
            os.path.relpath(image_path, start=json_path.parent)
        ).as_posix()

    project_definition = {
        "source_image": source_image,
        "image_rotation": normalize_rotation(image_rotation),
        "landmarks": {
            landmark.name: {
                "coordinates": (
                    [landmark.x, landmark.y] if landmark.is_placed else []
                )
            }
            for landmark in landmarks.values()
        },
        "landmarks_groups": {
            group.name: {
                "segments": [list(segment) for segment in group.segments],
                "angles": group.angles.copy(),
            }
            for group in groups.values()
        },
        "curves": {
            curve.name: {
                "point_count": curve.point_count,
                "start_landmark": curve.start_landmark,
                "end_landmark": curve.end_landmark,
            }
            for curve in (curves or {}).values()
        },
        "distances": {
            name: {"landmarks": list(landmark_pair)}
            for name, landmark_pair in (distances or {}).items()
        },
    }
    if main_axis is not None:
        project_definition["reference_axis"] = {
            "landmarks": [main_axis.start_landmark, main_axis.end_landmark],
            "angle_from_vertical": main_axis.angle_from_vertical,
        }

    return (
        json.dumps(
            {"project_definition": project_definition},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


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
        if value is None:
            angles.append(None)
            continue
        if isinstance(value, str):
            if value.lower() != "free":
                raise ValueError(
                    f"Unknown angle constraint '{value}' in group '{group_name}'"
                )
            angles.append(None)
            continue
        angle = _number(value, f"Angle in group '{group_name}'")
        if angle < -180 or angle > 180:
            raise ValueError(f"Angle in group '{group_name}' is outside -180..180")
        angles.append(angle)
    return [] if all(angle is None for angle in angles) else angles


def _point_from_json(value, description: str) -> QPointF:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{description} must contain two numbers")
    return QPointF(
        _number(value[0], f"{description} X coordinate"),
        _number(value[1], f"{description} Y coordinate"),
    )


def deserialize_json(
    content: str,
) -> tuple[
    dict[str, Landmark],
    dict[str, GroupDefinition],
    dict[str, CurveDefinition],
    dict[str, tuple[str, str]],
    MainAxisDefinition | None,
    float,
    list[str],
]:
    """Parse a saved JSON project definition without changing the GUI state."""

    try:
        data = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON: {error}") from error

    if not isinstance(data, dict):
        raise ValueError("The JSON root must be an object")
    project_definition = data.get("project_definition")
    if not isinstance(project_definition, dict):
        raise ValueError("project_definition must be an object")

    landmarks_data = project_definition.get("landmarks", {})
    if not isinstance(landmarks_data, dict):
        raise ValueError("landmarks must be an object")
    landmarks = {}
    for name, landmark_data in landmarks_data.items():
        if not isinstance(landmark_data, dict):
            raise ValueError(f"Landmark '{name}' must be an object")
        coordinates = landmark_data.get("coordinates", [])
        if coordinates == []:
            landmarks[name] = Landmark(name)
            continue
        point = _point_from_json(coordinates, f"Coordinates for landmark '{name}'")
        landmarks[name] = Landmark(name, point.x(), point.y())

    groups_data = project_definition.get("landmarks_groups", {})
    if not isinstance(groups_data, dict):
        raise ValueError("landmarks_groups must be an object")
    groups = {}
    for name, group_data in groups_data.items():
        if not isinstance(group_data, dict):
            raise ValueError(f"Group '{name}' must be an object")
        raw_segments = group_data.get("segments")
        if raw_segments is None:
            group_landmarks = group_data.get("landmarks")
            if not isinstance(group_landmarks, list) or not all(
                isinstance(item, str) for item in group_landmarks
            ):
                raise ValueError(f"Landmarks for group '{name}' must be strings")
            segments = list(zip(group_landmarks, group_landmarks[1:]))
        else:
            segments = []
        if not isinstance(raw_segments, list):
            if raw_segments is not None:
                raise ValueError(f"Segments for group '{name}' must be an array")
        if raw_segments is not None:
            for segment in raw_segments:
                if (
                    not isinstance(segment, list)
                    or len(segment) != 2
                    or not all(isinstance(item, str) for item in segment)
                ):
                    raise ValueError(
                        f"Each segment in group '{name}' must contain two landmarks"
                    )
                segments.append((segment[0], segment[1]))
        unknown = [
            item for segment in segments for item in segment if item not in landmarks
        ]
        if unknown:
            raise ValueError(
                f"Group '{name}' references unknown landmarks: {', '.join(unknown)}"
            )
        angles = _deserialize_angles(group_data.get("angles", []), name, len(segments))
        groups[name] = GroupDefinition(name, segments, angles)

    curves_data = project_definition.get("curves", {})
    if not isinstance(curves_data, dict):
        raise ValueError("curves must be an object")
    curves = {}
    for name, curve_data in curves_data.items():
        if not isinstance(curve_data, dict):
            raise ValueError(f"Curve '{name}' must be an object")
        point_count = curve_data.get("point_count")
        if isinstance(point_count, bool) or not isinstance(point_count, int):
            raise ValueError(f"Point count for curve '{name}' must be an integer")
        if point_count < 2:
            raise ValueError(f"Curve '{name}' must contain at least two points")
        start_landmark = curve_data.get("start_landmark")
        end_landmark = curve_data.get("end_landmark")
        if not isinstance(start_landmark, str) or not isinstance(end_landmark, str):
            raise ValueError(f"Curve '{name}' anchors must be landmark names")
        if start_landmark == end_landmark:
            raise ValueError(f"Curve '{name}' must use two different anchors")
        unknown = [
            landmark_name
            for landmark_name in (start_landmark, end_landmark)
            if landmark_name not in landmarks
        ]
        if unknown:
            raise ValueError(
                f"Curve '{name}' references unknown landmarks: {', '.join(unknown)}"
            )
        curves[name] = CurveDefinition(
            name, point_count, start_landmark, end_landmark
        )

    distances_data = project_definition.get("distances", {})
    if not isinstance(distances_data, dict):
        raise ValueError("distances must be an object")
    distances = {}
    for name, distance_data in distances_data.items():
        if not isinstance(distance_data, dict):
            raise ValueError(f"Distance '{name}' must be an object")
        distance_landmarks = distance_data.get("landmarks")
        if (
            not isinstance(distance_landmarks, list)
            or len(distance_landmarks) != 2
            or not all(isinstance(landmark_name, str) for landmark_name in distance_landmarks)
        ):
            raise ValueError(f"Distance '{name}' must define two landmark names")
        start_landmark, end_landmark = distance_landmarks
        if start_landmark == end_landmark:
            raise ValueError(f"Distance '{name}' must use two different landmarks")
        unknown = [
            landmark_name
            for landmark_name in distance_landmarks
            if landmark_name not in landmarks
        ]
        if unknown:
            raise ValueError(
                f"Distance '{name}' references unknown landmarks: {', '.join(unknown)}"
            )
        distances[name] = (start_landmark, end_landmark)

    image_rotation = normalize_rotation(
        _number(project_definition.get("image_rotation", 0), "image_rotation")
    )
    axis_data = project_definition.get("reference_axis")
    main_axis = None
    warnings = []
    if "reference_axis" not in project_definition and "main_axis" in project_definition:
        axis_data = project_definition["main_axis"]
        warnings.append("Loaded legacy 'main_axis' as 'reference_axis'.")
    if axis_data is not None:
        if not isinstance(axis_data, dict):
            raise ValueError("reference_axis must be an object")
        axis_landmarks = axis_data.get("landmarks")
        if (
            isinstance(axis_landmarks, list)
            and len(axis_landmarks) == 2
            and all(isinstance(name, str) for name in axis_landmarks)
        ):
            start_landmark, end_landmark = axis_landmarks
            if start_landmark == end_landmark:
                raise ValueError("The reference axis landmarks must be distinct")
            unknown = [
                name for name in axis_landmarks if name not in landmarks
            ]
            if unknown:
                raise ValueError(
                    "Reference axis references unknown landmarks: " + ", ".join(unknown)
                )
            angle_from_vertical = _number(
                axis_data.get("angle_from_vertical", 0),
                "Reference axis angle from vertical",
            )
            main_axis = MainAxisDefinition(
                start_landmark, end_landmark, normalize_rotation(angle_from_vertical)
            )
        else:
            raise ValueError("reference_axis must define two landmark names")

    return landmarks, groups, curves, distances, main_axis, image_rotation, warnings


class AngleWheel(QWidget):
    """Circular selector with discrete angles between -180 and 180 degrees."""

    angle_selected = Signal(int)

    def __init__(
        self,
        step: int,
        selected_angle: float | None = None,
        reference_angle: float = 0,
    ):
        super().__init__()
        self.step = step
        self.selected_angle = selected_angle
        self.reference_angle = reference_angle
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
        raw_angle = normalize_rotation(
            math.degrees(math.atan2(-dy, dx)) - self.reference_angle
        )
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
            display_radians = math.radians(angle + self.reference_angle)
            endpoint = QPointF(
                center.x() + radius * math.cos(display_radians),
                center.y() - radius * math.sin(display_radians),
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
                center.x() + label_radius * math.cos(display_radians),
                center.y() - label_radius * math.sin(display_radians),
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

    def __init__(
        self,
        step: int,
        selected_angle: float | None = None,
        incoming_angle: float = 180,
    ):
        super().__init__(step, selected_angle, incoming_angle)
        self.incoming_angle = incoming_angle

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) / 2 - 58
        painter.fillRect(self.rect(), QColor("#252525"))

        painter.setPen(QPen(QColor("#aaaaaa"), 5))
        incoming_radians = math.radians(self.incoming_angle)
        incoming_start = QPointF(
            center.x() - radius * math.cos(incoming_radians),
            center.y() + radius * math.sin(incoming_radians),
        )
        incoming_end = center
        painter.drawLine(incoming_start, incoming_end)
        self._draw_incoming_arrow(painter, incoming_start, incoming_end)
        painter.setPen(QPen(QColor("#aaaaaa"), 1, Qt.DashLine))
        painter.drawLine(center, QPointF(center.x() + radius, center.y()))

        for angle in self.available_angles:
            if angle == 180:
                continue
            radians = math.radians(angle + self.incoming_angle)
            endpoint = QPointF(
                center.x() + radius * math.cos(radians),
                center.y() - radius * math.sin(radians),
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
                center.y() - label_radius * math.sin(radians),
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
            "Negative turn: clockwise",
        )
        painter.setPen(QPen(QColor("#ff8b68"), 1))
        painter.drawText(
            QRectF(0, self.height() - 29, self.width(), 24),
            Qt.AlignCenter,
            "Positive turn: counterclockwise",
        )
        painter.setPen(QPen(QColor("#dddddd"), 1))
        painter.drawText(
            QRectF(incoming_start.x() - 10, center.y() - 28, radius, 20),
            Qt.AlignCenter,
            "Incoming segment",
        )

    @staticmethod
    def _draw_incoming_arrow(painter: QPainter, start: QPointF, end: QPointF):
        """Draw an arrow whose tip is at the incoming segment endpoint."""

        direction = math.atan2(end.y() - start.y(), end.x() - start.x())
        wing_length = 16
        wing_angle = math.radians(145)
        for offset in (-wing_angle, wing_angle):
            wing_end = QPointF(
                end.x() + wing_length * math.cos(direction + offset),
                end.y() + wing_length * math.sin(direction + offset),
            )
            painter.drawLine(end, wing_end)


class AngleSelectionDialog(QDialog):
    """Dialog for imposing or clearing one segment angle."""

    def __init__(
        self,
        segment_name: str,
        step: int,
        selected_angle: float | None,
        relative: bool,
        reference_angle: float = 0,
        incoming_angle: float = 180,
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
            else "Click a compass ray to set the angle relative to image vertical."
        )
        instruction = QLabel(instruction_text)
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        selector_class = RelativeAngleDiagram if relative else AngleWheel
        self.selector = (
            RelativeAngleDiagram(step, selected_angle, incoming_angle)
            if relative
            else AngleWheel(step, selected_angle, reference_angle)
        )
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


class AxisAlignmentDialog(QDialog):
    """Choose how the reference axis is aligned on screen."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.alignment = "vertical"
        self.setWindowTitle("Set reference axis alignment")
        layout = QVBoxLayout(self)
        instruction = QLabel(
            "Choose how the image should be rotated to align the reference axis."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        vertical_button = QPushButton("Vertical (same X coordinate)")
        horizontal_button = QPushButton("Horizontal (same Y coordinate)")
        vertical_button.clicked.connect(lambda: self._select_alignment("vertical"))
        horizontal_button.clicked.connect(
            lambda: self._select_alignment("horizontal")
        )
        layout.addWidget(vertical_button)
        layout.addWidget(horizontal_button)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_alignment(self, alignment: str):
        self.alignment = alignment
        self.accept()


class ImageCanvas(QWidget):
    """Display an image and emit clicks in original-image coordinates."""

    image_clicked = Signal(QPointF)
    zoom_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.source_pixmap = QPixmap()
        self.pixmap = QPixmap()
        self.source_to_display = QTransform()
        self.display_to_source = QTransform()
        self.rotation_degrees = 0.0
        self.zoom_factor = 1.0
        self.view_center = QPointF(0, 0)
        self.landmarks: dict[str, Landmark] = {}
        self.groups: dict[str, GroupDefinition] = {}
        self.distances: dict[str, tuple[str, str]] = {}
        self.main_axis: MainAxisDefinition | None = None
        self.pending_axis_points: list[QPointF] = []
        self.selected_landmark = ""
        self._pan_start_position: QPointF | None = None
        self._pan_last_position: QPointF | None = None
        self._pan_moved = False
        self.setMinimumSize(500, 400)
        self.setCursor(Qt.CrossCursor)
        self.view_mode = "photograph"

        self.zoom_controls = QWidget(self)
        controls_layout = QHBoxLayout(self.zoom_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        self.zoom_in_button = QPushButton("Zoom +")
        self.zoom_out_button = QPushButton("Zoom -")
        self.fit_image_button = QPushButton("Fit image")
        controls_layout.addWidget(self.zoom_in_button)
        controls_layout.addWidget(self.zoom_out_button)
        controls_layout.addWidget(self.fit_image_button)
        self.zoom_controls.adjustSize()

    def set_view_mode(self, mode: str):
        """Set the overlay combination displayed on the canvas."""

        if mode not in {"photograph", "idealized", "distances"}:
            raise ValueError(f"Unknown image view mode: {mode}")
        self.view_mode = mode
        self.update()

    def set_image(self, image_path: pl.Path) -> bool:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return False
        self.source_pixmap = pixmap
        self.set_rotation(0)
        return True

    def set_rotation(self, angle: float):
        self.rotation_degrees = normalize_rotation(angle)
        if self.source_pixmap.isNull():
            return
        rotation = QTransform().rotate(self.rotation_degrees)
        self.source_to_display = QPixmap.trueMatrix(
            rotation, self.source_pixmap.width(), self.source_pixmap.height()
        )
        self.display_to_source, invertible = self.source_to_display.inverted()
        if not invertible:
            raise ValueError("The image rotation transform is not invertible")
        self.pixmap = self.source_pixmap.transformed(rotation, Qt.SmoothTransformation)
        self.zoom_factor = 1.0
        self.view_center = QPointF(self.pixmap.width() / 2, self.pixmap.height() / 2)
        self.zoom_changed.emit(self.zoom_factor)
        self.update()

    def image_rect(self) -> QRectF:
        if self.pixmap.isNull():
            return QRectF()
        scale = (
            min(
                self.width() / self.pixmap.width(), self.height() / self.pixmap.height()
            )
            * self.zoom_factor
        )
        width = self.pixmap.width() * scale
        height = self.pixmap.height() * scale
        return QRectF(
            self.width() / 2 - self.view_center.x() * scale,
            self.height() / 2 - self.view_center.y() * scale,
            width,
            height,
        )

    def zoom_by(self, factor: float, anchor: QPointF | None = None):
        """Zoom around a widget point while preserving its image location."""

        if self.pixmap.isNull() or factor <= 0:
            return
        old_rect = self.image_rect()
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        old_scale = old_rect.width() / self.pixmap.width()
        if old_scale == 0:
            return
        display_point = QPointF(
            (anchor.x() - old_rect.left()) / old_scale,
            (anchor.y() - old_rect.top()) / old_scale,
        )
        self.zoom_factor = max(0.25, min(20.0, self.zoom_factor * factor))
        new_scale = (
            min(
                self.width() / self.pixmap.width(),
                self.height() / self.pixmap.height(),
            )
            * self.zoom_factor
        )
        self.view_center = QPointF(
            display_point.x() - (anchor.x() - self.width() / 2) / new_scale,
            display_point.y() - (anchor.y() - self.height() / 2) / new_scale,
        )
        self.zoom_changed.emit(self.zoom_factor)
        self.update()

    def reset_zoom(self):
        """Fit the rotated image to the canvas."""

        self.zoom_factor = 1.0
        self.view_center = QPointF(self.pixmap.width() / 2, self.pixmap.height() / 2)
        self.zoom_changed.emit(self.zoom_factor)
        self.update()

    def image_to_widget(self, point: QPointF) -> QPointF:
        rect = self.image_rect()
        display_point = self.source_to_display.map(point)
        return QPointF(
            rect.left() + display_point.x() * rect.width() / self.pixmap.width(),
            rect.top() + display_point.y() * rect.height() / self.pixmap.height(),
        )

    def widget_to_image(self, point: QPointF) -> QPointF | None:
        rect = self.image_rect()
        if rect.isEmpty() or not rect.contains(point):
            return None
        display_point = QPointF(
            (point.x() - rect.left()) * self.pixmap.width() / rect.width(),
            (point.y() - rect.top()) * self.pixmap.height() / rect.height(),
        )
        return self.display_to_source.map(display_point)

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
        self._pan_start_position = event.position()
        self._pan_last_position = event.position()
        self._pan_moved = False
        self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            self._pan_start_position is None
            or self._pan_last_position is None
            or not event.buttons() & Qt.LeftButton
        ):
            return

        total_delta = event.position() - self._pan_start_position
        if not self._pan_moved and total_delta.manhattanLength() < 4:
            return

        scale = self.image_rect().width() / self.pixmap.width()
        if scale == 0:
            return
        delta = event.position() - self._pan_last_position
        self.view_center -= QPointF(delta.x() / scale, delta.y() / scale)
        self._pan_last_position = event.position()
        self._pan_moved = True
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton or self._pan_start_position is None:
            return

        start_position = self._pan_start_position
        was_moved = self._pan_moved
        self._pan_start_position = None
        self._pan_last_position = None
        self._pan_moved = False
        self.setCursor(Qt.CrossCursor)
        if not was_moved:
            image_point = self.widget_to_image(start_position)
            if image_point is not None:
                self.image_clicked.emit(image_point)
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        if self.pixmap.isNull() or event.angleDelta().y() == 0:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120
        self.zoom_by(1.2**steps, event.position())
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.zoom_controls.adjustSize()
        self.zoom_controls.move(12, 12)

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
        if self.view_mode == "photograph":
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        elif self.view_mode == "idealized":
            landmark_points, group_segments = self._idealized_group_geometry()
            self._draw_idealized_groups(painter, group_segments)
            self._draw_landmarks(painter, landmark_points)
            return
        else:
            self._draw_distances(painter)
        self._draw_landmarks(painter)

    def _landmark_point(self, name: str) -> QPointF | None:
        landmark = self.landmarks.get(name)
        if landmark is None or not landmark.is_placed:
            return None
        return self.image_to_widget(QPointF(landmark.x, landmark.y))

    def _idealized_group_geometry(self):
        """Return group geometry reconstructed from the imposed segment angles."""

        landmark_points = {
            landmark.name: self.image_to_widget(QPointF(landmark.x, landmark.y))
            for landmark in self.landmarks.values()
            if landmark.is_placed
        }
        group_segments = []
        for group in self.groups.values():
            headings = {}
            for index, (start, end) in enumerate(group.segments):
                source_start = self._landmark_point(start)
                source_end = self._landmark_point(end)
                start_point = landmark_points.get(start)
                if source_start is None or source_end is None or start_point is None:
                    continue
                length = math.hypot(
                    source_end.x() - source_start.x(),
                    source_end.y() - source_start.y(),
                )
                original_heading = trigonometric_heading(source_start, source_end)
                angle = group.angles[index] if index < len(group.angles) else None
                incoming_index = next(
                    (
                        previous_index
                        for previous_index, segment in reversed(
                            list(enumerate(group.segments[:index]))
                        )
                        if segment[1] == start
                    ),
                    None,
                )
                if angle is None:
                    heading = original_heading
                elif incoming_index is None or incoming_index not in headings:
                    heading = normalize_rotation(90 + angle)
                else:
                    heading = normalize_rotation(headings[incoming_index] + angle)
                radians = math.radians(heading)
                end_point = QPointF(
                    start_point.x() + length * math.cos(radians),
                    start_point.y() - length * math.sin(radians),
                )
                landmark_points[end] = end_point
                headings[index] = heading
                group_segments.append((start_point, end_point, angle, index))
        return landmark_points, group_segments

    def _draw_idealized_groups(self, painter: QPainter, group_segments):
        painter.setPen(QPen(QColor(60, 180, 255, 200), 3))
        for first, second, angle, index in group_segments:
            painter.drawLine(first, second)
            if angle is not None:
                self._draw_arrow_head(painter, first, second)
                midpoint = (first + second) / 2
                painter.setPen(QPen(QColor(255, 210, 50), 1))
                suffix = "absolute" if index == 0 else "turn"
                painter.drawText(midpoint + QPointF(6, -6), f"{angle:g}° {suffix}")
                painter.setPen(QPen(QColor(60, 180, 255, 200), 3))

    def _draw_groups(self, painter: QPainter):
        painter.setPen(QPen(QColor(60, 180, 255, 200), 3))
        for group in self.groups.values():
            for index, (start, end) in enumerate(group.segments):
                first = self._landmark_point(start)
                second = self._landmark_point(end)
                if first is not None and second is not None:
                    painter.drawLine(first, second)
                    angle = group.angles[index] if index < len(group.angles) else None
                    if angle is not None:
                        self._draw_arrow_head(painter, first, second)
                        midpoint = (first + second) / 2
                        painter.setPen(QPen(QColor(255, 210, 50), 1))
                        suffix = "absolute" if index == 0 else "turn"
                        painter.drawText(
                            midpoint + QPointF(6, -6), f"{angle:g}° {suffix}"
                        )
                        painter.setPen(QPen(QColor(60, 180, 255, 200), 3))

    def _draw_distances(self, painter: QPainter):
        painter.setPen(QPen(QColor(255, 175, 60), 3))
        for name, (start, end) in self.distances.items():
            first = self._landmark_point(start)
            second = self._landmark_point(end)
            if first is None or second is None:
                continue
            painter.drawLine(first, second)
            midpoint = (first + second) / 2
            painter.setPen(QPen(QColor(255, 230, 160), 1))
            painter.drawText(midpoint + QPointF(6, -6), name)
            painter.setPen(QPen(QColor(255, 175, 60), 3))

    def _draw_arrow_head(self, painter: QPainter, start: QPointF, end: QPointF):
        direction = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_length = 12
        for offset in (-2.6, 2.6):
            arrow_end = QPointF(
                end.x() + arrow_length * math.cos(direction + offset),
                end.y() + arrow_length * math.sin(direction + offset),
            )
            painter.drawLine(end, arrow_end)

    def _draw_main_axis(self, painter: QPainter):
        if self.main_axis is None:
            self._draw_pending_axis_origin(painter)
            return
        points = axis_landmark_points(self.main_axis, self.landmarks)
        if points is None:
            self._draw_pending_axis_origin(painter)
            return
        origin = self.image_to_widget(points[0])
        destination = self.image_to_widget(points[1])
        painter.setPen(QPen(QColor("#ff40d7"), 4))
        painter.drawLine(origin, destination)
        self._draw_arrow_head(painter, origin, destination)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(origin, 6, 6)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawText(origin + QPointF(8, -8), "Anterior end")
        self._draw_pending_axis_origin(painter)

    def _draw_pending_axis_origin(self, painter: QPainter):
        if not self.pending_axis_points:
            return
        origin = self.image_to_widget(self.pending_axis_points[0])
        painter.setPen(QPen(QColor("#ff40d7"), 3))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(origin, 6, 6)
        painter.drawText(origin + QPointF(8, -8), "Selected reference axis landmark")

    def _draw_landmarks(
        self, painter: QPainter, landmark_points: dict[str, QPointF] | None = None
    ):
        for landmark in self.landmarks.values():
            if not landmark.is_placed:
                continue
            point = (
                landmark_points.get(landmark.name)
                if landmark_points is not None
                else self.image_to_widget(QPointF(landmark.x, landmark.y))
            )
            if point is None:
                continue
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

    def __init__(self, project_path: pl.Path | None = None):
        super().__init__()
        self.project_path = project_path
        self.image_path: pl.Path | None = None
        self.output_path: pl.Path | None = None
        self.landmarks: dict[str, Landmark] = {}
        self.groups: dict[str, GroupDefinition] = {}
        self.curves: dict[str, CurveDefinition] = {}
        self.distances: dict[str, tuple[str, str]] = {}
        self.main_axis: MainAxisDefinition | None = None
        self.image_rotation = 0.0
        self.mode = "idle"
        self.pending_name = ""
        self.pending_segments: list[tuple[str, str]] = []
        self.pending_segment_start: str | None = None
        self.pending_axis_points: list[QPointF] = []
        self.pending_axis_landmark: str | None = None
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
        self.canvas.distances = self.distances
        self.canvas.main_axis = self.main_axis
        self.canvas.pending_axis_points = self.pending_axis_points
        self.canvas.image_clicked.connect(self._handle_canvas_click)
        self.canvas.zoom_in_button.clicked.connect(self._zoom_in)
        self.canvas.zoom_out_button.clicked.connect(self._zoom_out)
        self.canvas.fit_image_button.clicked.connect(self._fit_image)

        self.setCentralWidget(self.canvas)
        self.landmark_panel = self._create_panel(
            "Landmarks", self._build_landmark_group(), 360, 360
        )
        self.reference_axis_panel = self._create_panel(
            "Reference axis", self._build_reference_axis_section(), 400, 210
        )
        self.group_panel = self._create_panel(
            "Groups", self._build_group_section(), 500, 330
        )
        self.curve_panel = self._create_panel(
            "Curves", self._build_curve_section(), 360, 300
        )
        self.distance_panel = self._create_panel(
            "Morphometric distances", self._build_distance_section(), 400, 300
        )

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.zoom_label = QLabel("Zoom: 100%")
        self.status_bar.addPermanentWidget(self.zoom_label)
        self.canvas.zoom_changed.connect(self._update_zoom_label)
        self.status_bar.showMessage("Open an image to begin")

    def _create_panel(
        self, title: str, content: QWidget, width: int, height: int
    ) -> QDockWidget:
        """Create a floating editor panel shown from the Panels menu."""

        panel = QDockWidget(title, self)
        panel.setAllowedAreas(Qt.NoDockWidgetArea)
        panel.setWidget(content)
        self.addDockWidget(Qt.RightDockWidgetArea, panel)
        panel.setFloating(True)
        panel.resize(width, height)
        panel.hide()
        return panel

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

    def _build_group_section(self) -> QGroupBox:
        group = QGroupBox("Groups")
        layout = QVBoxLayout(group)
        self.group_name_edit = QLineEdit()
        self.group_name_edit.setPlaceholderText("Unique group name")
        layout.addWidget(self.group_name_edit)
        buttons = QHBoxLayout()
        self.define_group_button = QPushButton("Add group")
        self.add_segment_button = QPushButton("Add segment")
        self.cancel_group_button = QPushButton("Cancel")
        self.delete_group_button = QPushButton("Delete selected")
        buttons.addWidget(self.define_group_button)
        buttons.addWidget(self.add_segment_button)
        buttons.addWidget(self.cancel_group_button)
        buttons.addWidget(self.delete_group_button)
        layout.addLayout(buttons)
        rotation_layout = QHBoxLayout()
        rotation_layout.addWidget(QLabel("Group rotation (°):"))
        self.group_rotation_edit = QLineEdit()
        self.group_rotation_edit.setPlaceholderText("Positive: counterclockwise")
        self.rotate_group_button = QPushButton("Rotate selected group")
        rotation_layout.addWidget(self.group_rotation_edit)
        rotation_layout.addWidget(self.rotate_group_button)
        layout.addLayout(rotation_layout)
        self.group_list = QListWidget()
        self.group_list.setMinimumHeight(100)
        layout.addWidget(self.group_list)
        self.define_group_button.clicked.connect(self._start_group)
        self.add_segment_button.clicked.connect(self._start_add_segment)
        self.cancel_group_button.clicked.connect(self._cancel_definition)
        self.delete_group_button.clicked.connect(self._delete_group)
        self.rotate_group_button.clicked.connect(self._rotate_selected_group)
        return group

    def _build_reference_axis_section(self) -> QGroupBox:
        group = QGroupBox("Reference axis")
        layout = QVBoxLayout(group)
        description = QLabel(
            "By default, the reference axis is the vertical image axis."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        self.axis_start_combo = QComboBox()
        self.axis_end_combo = QComboBox()
        self.axis_alignment_combo = QComboBox()
        self.axis_alignment_combo.addItem("Vertical", 0)
        self.axis_alignment_combo.addItem("Horizontal", -90)
        form.addRow("Start anchor:", self.axis_start_combo)
        form.addRow("End anchor:", self.axis_end_combo)
        form.addRow("Alignment:", self.axis_alignment_combo)
        layout.addLayout(form)
        self.update_axis_button = QPushButton("Update reference axis")
        self.define_axis_button = QPushButton("Define from image")
        self.clear_axis_button = QPushButton("Use image vertical default")
        layout.addWidget(self.update_axis_button)
        layout.addWidget(self.define_axis_button)
        layout.addWidget(self.clear_axis_button)
        self.update_axis_button.clicked.connect(self._update_reference_axis)
        self.define_axis_button.clicked.connect(self._start_axis_definition)
        self.clear_axis_button.clicked.connect(self._clear_axis)
        return group

    def _build_curve_section(self) -> QGroupBox:
        group = QGroupBox("Curves")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        self.curve_name_edit = QLineEdit()
        self.curve_name_edit.setPlaceholderText("Unique curve name")
        self.curve_point_count_spin = QSpinBox()
        self.curve_point_count_spin.setRange(2, 10000)
        self.curve_point_count_spin.setValue(8)
        self.curve_start_combo = QComboBox()
        self.curve_end_combo = QComboBox()
        form.addRow("Name:", self.curve_name_edit)
        form.addRow("Points:", self.curve_point_count_spin)
        form.addRow("Start anchor:", self.curve_start_combo)
        form.addRow("End anchor:", self.curve_end_combo)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.add_curve_button = QPushButton("Add curve")
        self.update_curve_button = QPushButton("Update selected")
        self.delete_curve_button = QPushButton("Delete selected")
        buttons.addWidget(self.add_curve_button)
        buttons.addWidget(self.update_curve_button)
        buttons.addWidget(self.delete_curve_button)
        layout.addLayout(buttons)

        self.curve_list = QListWidget()
        self.curve_list.setMinimumHeight(100)
        layout.addWidget(self.curve_list)
        self.add_curve_button.clicked.connect(self._add_curve)
        self.update_curve_button.clicked.connect(self._update_curve)
        self.delete_curve_button.clicked.connect(self._delete_curve)
        self.curve_list.currentItemChanged.connect(self._load_selected_curve)
        return group

    def _build_distance_section(self) -> QGroupBox:
        group = QGroupBox("Morphometric distances")
        layout = QVBoxLayout(group)
        form = QFormLayout()
        self.distance_name_edit = QLineEdit()
        self.distance_name_edit.setPlaceholderText("Unique distance name")
        self.distance_start_combo = QComboBox()
        self.distance_end_combo = QComboBox()
        form.addRow("Name:", self.distance_name_edit)
        form.addRow("First landmark:", self.distance_start_combo)
        form.addRow("Second landmark:", self.distance_end_combo)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.add_distance_button = QPushButton("Add distance")
        self.delete_distance_button = QPushButton("Delete selected")
        buttons.addWidget(self.add_distance_button)
        buttons.addWidget(self.delete_distance_button)
        layout.addLayout(buttons)

        self.distance_list = QListWidget()
        self.distance_list.setMinimumHeight(100)
        layout.addWidget(self.distance_list)
        self.add_distance_button.clicked.connect(self._add_distance)
        self.delete_distance_button.clicked.connect(self._delete_distance)
        return group

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open image...", self)
        save_action = QAction("Save JSON...", self)
        exit_action = QAction("Exit", self)
        open_action.setShortcut("Ctrl+O")
        save_action.setShortcut("Ctrl+S")
        open_action.triggered.connect(self.open_image)
        save_action.triggered.connect(self.save_json)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        image_view_menu = self.menuBar().addMenu("Image view")
        image_view_group = QActionGroup(self)
        image_view_group.setExclusive(True)
        for label, mode in (
            ("Photograph with landmarks", "photograph"),
            ("Idealized groups", "idealized"),
            ("Distance definitions", "distances"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(mode == "photograph")
            action.triggered.connect(
                lambda checked, selected_mode=mode: (
                    self._set_image_view(selected_mode) if checked else None
                )
            )
            image_view_group.addAction(action)
            image_view_menu.addAction(action)

        panels_menu = self.menuBar().addMenu("Project setup")
        panels_menu.addAction(self.landmark_panel.toggleViewAction())
        panels_menu.addAction(self.reference_axis_panel.toggleViewAction())
        panels_menu.addAction(self.group_panel.toggleViewAction())
        panels_menu.addAction(self.curve_panel.toggleViewAction())
        panels_menu.addAction(self.distance_panel.toggleViewAction())

        self.save_action = save_action
        self.save_action.setEnabled(False)

    def _update_zoom_label(self, _value: float | None = None):
        self.zoom_label.setText(f"Zoom: {self.canvas.zoom_factor:.0%}")

    def _zoom_in(self):
        self.canvas.zoom_by(1.2)

    def _zoom_out(self):
        self.canvas.zoom_by(1 / 1.2)

    def _fit_image(self):
        self.canvas.reset_zoom()

    def _set_image_view(self, mode: str):
        self.canvas.set_view_mode(mode)

    def _set_editor_enabled(self, enabled: bool):
        for widget in (
            self.axis_start_combo,
            self.axis_end_combo,
            self.axis_alignment_combo,
            self.update_axis_button,
            self.define_axis_button,
            self.clear_axis_button,
            self.landmark_name_edit,
            self.add_landmark_button,
            self.place_landmark_button,
            self.rename_landmark_button,
            self.delete_landmark_button,
            self.landmark_list,
            self.group_name_edit,
            self.define_group_button,
            self.add_segment_button,
            self.cancel_group_button,
            self.delete_group_button,
            self.group_rotation_edit,
            self.rotate_group_button,
            self.group_list,
            self.curve_name_edit,
            self.curve_point_count_spin,
            self.curve_start_combo,
            self.curve_end_combo,
            self.add_curve_button,
            self.update_curve_button,
            self.delete_curve_button,
            self.curve_list,
            self.distance_name_edit,
            self.distance_start_combo,
            self.distance_end_combo,
            self.add_distance_button,
            self.delete_distance_button,
            self.distance_list,
        ):
            widget.setEnabled(enabled)
        for button in (
            self.canvas.zoom_in_button,
            self.canvas.zoom_out_button,
            self.canvas.fit_image_button,
        ):
            button.setEnabled(enabled)
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
        self.curves = {}
        self.distances = {}
        self.main_axis = None
        self.image_rotation = 0.0
        self.mode = "idle"
        self.pending_segments.clear()
        self.pending_segment_start = None
        self.pending_axis_points.clear()
        self.pending_axis_landmark = None
        status_message = "Image loaded. Add a landmark to begin."
        configuration_path = image_path.with_suffix(".json")
        if self.project_path is not None:
            try:
                project = load_project(self.project_path)
                definitions = project["definitions"]
                if definitions:
                    content = json.dumps({"project_definition": definitions})
                    (
                        self.landmarks,
                        self.groups,
                        self.curves,
                        self.distances,
                        self.main_axis,
                        self.image_rotation,
                        warnings,
                    ) = deserialize_json(content)
                    status_message = f"Loaded definitions from {self.project_path.name}"
                    if warnings:
                        QMessageBox.warning(self, "Load project", "\n".join(warnings))
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "Load project", str(error))
        elif configuration_path.is_file():
            try:
                content = configuration_path.read_text(encoding="utf-8")
                (
                    self.landmarks,
                    self.groups,
                    self.curves,
                    self.distances,
                    self.main_axis,
                    self.image_rotation,
                    warnings,
                ) = deserialize_json(content)
            except (OSError, ValueError) as error:
                QMessageBox.critical(
                    self,
                    "Load JSON",
                    f"Could not load {configuration_path.name}:\n{error}",
                )
            else:
                self.output_path = configuration_path
                status_message = f"Loaded configuration from {configuration_path.name}"
                if warnings:
                    QMessageBox.warning(self, "Load JSON", "\n".join(warnings))
        self._sync_canvas_data()
        self.canvas.set_rotation(self.image_rotation)
        self._refresh_lists()
        self._set_editor_enabled(True)
        self.dirty = False
        self.setWindowTitle(f"{image_path.name} - SMORPHILA Landmark Definition Editor")
        self.status_bar.showMessage(status_message)

    def _start_axis_definition(self):
        self.mode = "axis"
        self.pending_axis_points.clear()
        self.pending_axis_landmark = None
        self.status_bar.showMessage("Click the first reference axis landmark.")
        self.canvas.update()

    def _clear_axis(self):
        self.main_axis = None
        self.pending_axis_points.clear()
        self.pending_axis_landmark = None
        self.canvas.main_axis = None
        self.image_rotation = 0.0
        self.canvas.set_rotation(self.image_rotation)
        self.mode = "idle"
        self.dirty = True
        self._refresh_axis_landmark_choices()
        self._refresh_groups()
        self.canvas.update()
        self.status_bar.showMessage("Reference axis reset to the image vertical.")

    def _update_reference_axis(self):
        start_landmark = self.axis_start_combo.currentText()
        end_landmark = self.axis_end_combo.currentText()
        if not start_landmark or not end_landmark:
            QMessageBox.warning(
                self, "Reference axis", "Add two landmarks before defining an axis."
            )
            return
        if start_landmark == end_landmark:
            QMessageBox.warning(
                self, "Reference axis", "Select two different anchor landmarks."
            )
            return
        self.main_axis = MainAxisDefinition(
            start_landmark,
            end_landmark,
            float(self.axis_alignment_combo.currentData()),
        )
        self.canvas.main_axis = self.main_axis
        self.image_rotation = 0.0
        self.canvas.set_rotation(self.image_rotation)
        self.pending_axis_points.clear()
        self.pending_axis_landmark = None
        self.mode = "idle"
        self._align_main_axis()
        self.dirty = True
        self._refresh_axis_landmark_choices()
        self._refresh_groups()
        self.canvas.update()
        self.status_bar.showMessage("Reference axis updated.")

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
        self.pending_axis_points.clear()
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
        self.pending_axis_points.clear()
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
            group.segments = [
                tuple(new_name if name == old_name else name for name in segment)
                for segment in group.segments
            ]
        for curve in self.curves.values():
            if curve.start_landmark == old_name:
                curve.start_landmark = new_name
            if curve.end_landmark == old_name:
                curve.end_landmark = new_name
        self.distances = {
            distance_name: tuple(
                new_name if landmark_name == old_name else landmark_name
                for landmark_name in landmark_pair
            )
            for distance_name, landmark_pair in self.distances.items()
        }
        if self.main_axis is not None:
            if self.main_axis.start_landmark == old_name:
                self.main_axis.start_landmark = new_name
            if self.main_axis.end_landmark == old_name:
                self.main_axis.end_landmark = new_name
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
            f"group '{group.name}'"
            for group in self.groups.values()
            if any(name in segment for segment in group.segments)
        ]
        references.extend(
            f"curve '{curve.name}'"
            for curve in self.curves.values()
            if name in (curve.start_landmark, curve.end_landmark)
        )
        references.extend(
            f"distance '{distance_name}'"
            for distance_name, landmark_pair in self.distances.items()
            if name in landmark_pair
        )
        landmark = self.landmarks[name]
        if self.main_axis is not None and name in (
            self.main_axis.start_landmark,
            self.main_axis.end_landmark,
        ):
            references.append("the reference axis")
        if references:
            QMessageBox.warning(
                self,
                "Landmark",
                "Delete the following definitions first: "
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

    def _defined_segment_heading(
        self,
        group: GroupDefinition,
        index: int,
        visited: set[int] | None = None,
    ) -> float:
        """Return a segment heading using imposed angles where available."""

        visited = set() if visited is None else visited
        if index in visited:
            return 180.0
        visited.add(index)
        start, end = group.segments[index]
        imposed = group.angles[index] if index < len(group.angles) else None
        incoming = next(
            (
                (candidate_index, segment)
                for candidate_index, segment in reversed(
                    list(enumerate(group.segments[:index]))
                )
                if segment[1] == start
            ),
            None,
        )
        if imposed is not None:
            if incoming is not None:
                previous_heading = self._defined_segment_heading(
                    group, incoming[0], visited
                )
                return normalize_rotation(previous_heading + imposed)
            return normalize_rotation(90 + imposed)
        start_point = self.landmarks[start]
        end_point = self.landmarks[end]
        if start_point.is_placed and end_point.is_placed:
            return trigonometric_heading(
                self.canvas.image_to_widget(QPointF(start_point.x, start_point.y)),
                self.canvas.image_to_widget(QPointF(end_point.x, end_point.y)),
            )
        return 180.0

    def _main_axis_heading(self) -> float:
        if self.canvas.main_axis is None:
            return 90.0
        axis = self.canvas.main_axis
        points = axis_landmark_points(axis, self.landmarks)
        if points is None:
            return 0.0
        return trigonometric_heading(
            self.canvas.image_to_widget(points[0]),
            self.canvas.image_to_widget(points[1]),
        )

    @staticmethod
    def _ensure_segment_angles(group: GroupDefinition):
        segment_count = len(group.segments)
        if not group.angles:
            group.angles = [None] * segment_count
        elif len(group.angles) < segment_count:
            group.angles.extend([None] * (segment_count - len(group.angles)))

    @staticmethod
    def _compact_free_angles(group: GroupDefinition):
        if group.angles and all(angle is None for angle in group.angles):
            group.angles.clear()

    def _capture_reference_points(
        self, group: GroupDefinition, *landmark_names: str
    ):
        """Store landmark positions before a group rotation can move them."""

        for name in landmark_names:
            landmark = self.landmarks[name]
            if landmark.is_placed:
                group.reference_points.setdefault(name, (landmark.x, landmark.y))

    @staticmethod
    def _dependent_segment_indices(
        group: GroupDefinition, start_index: int
    ) -> list[int]:
        """Return a segment and all later segments attached to its endpoint."""

        affected = [start_index]
        affected_landmarks = {group.segments[start_index][1]}
        for index, (start, end) in enumerate(
            group.segments[start_index + 1 :], start_index + 1
        ):
            if start in affected_landmarks:
                affected.append(index)
                affected_landmarks.add(end)
        return affected

    def _apply_group_geometry(self, group: GroupDefinition, start_index: int):
        """Update an articulated chain while preserving every affected length."""

        affected_indices = self._dependent_segment_indices(group, start_index)

        original_geometry = {}
        for index in affected_indices:
            start, end = group.segments[index]
            start_landmark = self.landmarks[start]
            end_landmark = self.landmarks[end]
            if not start_landmark.is_placed or not end_landmark.is_placed:
                continue
            start_point = QPointF(start_landmark.x, start_landmark.y)
            end_point = QPointF(end_landmark.x, end_landmark.y)
            reference_start = group.reference_points.get(start)
            reference_end = group.reference_points.get(end)
            if reference_start is None or reference_end is None:
                length = math.hypot(
                    end_point.x() - start_point.x(), end_point.y() - start_point.y()
                )
            else:
                length = math.hypot(
                    reference_end[0] - reference_start[0],
                    reference_end[1] - reference_start[1],
                )
            original_geometry[index] = (
                length,
                trigonometric_heading(
                    self.canvas.image_to_widget(start_point),
                    self.canvas.image_to_widget(end_point),
                ),
            )

        for index in affected_indices:
            if index not in original_geometry:
                continue
            start, end = group.segments[index]
            imposed = group.angles[index] if index < len(group.angles) else None
            length, original_heading = original_geometry[index]
            incoming = next(
                (
                    previous_index
                    for previous_index, segment in reversed(
                        list(enumerate(group.segments[:index]))
                    )
                    if segment[1] == start
                ),
                None,
            )
            if imposed is None:
                heading = original_heading
            elif incoming is None:
                heading = normalize_rotation(90 + imposed)
            else:
                # Each distal turn is relative to the complete heading of its
                # incoming segment, including all proximal imposed turns.
                heading = normalize_rotation(
                    self._defined_segment_heading(group, incoming) + imposed
                )

            start_landmark = self.landmarks[start]
            display_start = self.canvas.source_to_display.map(
                QPointF(start_landmark.x, start_landmark.y)
            )
            radians = math.radians(heading)
            display_end = QPointF(
                display_start.x() + length * math.cos(radians),
                display_start.y() - length * math.sin(radians),
            )
            end_point = self.canvas.display_to_source.map(display_end)
            self.landmarks[end].x = end_point.x()
            self.landmarks[end].y = end_point.y()

    def _start_group(self):
        name = self._clean_name(self.group_name_edit, "Group", self.groups)
        if name is None:
            return
        self.groups[name] = GroupDefinition(name, [])
        self.group_name_edit.clear()
        self._refresh_groups()
        self._select_group_by_name(name)
        self.dirty = True
        self.status_bar.showMessage(f"Group '{name}' created. Add a segment to it.")

    def _start_add_segment(self):
        group_name = self._selected_group_name()
        if group_name is None:
            QMessageBox.warning(self, "Group", "Select an ordinary group first.")
            return
        if len([item for item in self.landmarks.values() if item.is_placed]) < 2:
            QMessageBox.warning(self, "Group", "Place at least two landmarks first.")
            return
        self.mode = "segment"
        self.pending_name = group_name
        self.pending_segment_start = None
        self.status_bar.showMessage("Click the segment start landmark.")

    def _cancel_definition(self):
        if self.mode not in {"axis", "segment"}:
            return
        self.mode = "idle"
        self.pending_name = ""
        self.pending_segment_start = None
        self.pending_axis_points.clear()
        self.pending_axis_landmark = None
        self.canvas.update()
        self.status_bar.showMessage("Definition cancelled.")

    def _add_segment_with_angle(self, group: GroupDefinition, start: str, end: str):
        incoming = next(
            (
                (candidate_index, segment)
                for candidate_index, segment in reversed(
                    list(enumerate(group.segments))
                )
                if segment[1] == start
            ),
            None,
        )
        incoming_angle = (
            self._defined_segment_heading(group, incoming[0])
            if incoming is not None
            else 180.0
        )
        dialog = AngleSelectionDialog(
            f"{start} → {end}",
            ANGLE_SELECTION_STEP,
            None,
            relative=incoming is not None,
            reference_angle=90,
            incoming_angle=incoming_angle,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        self._capture_reference_points(group, start, end)
        group.segments.append((start, end))
        if group.angles or dialog.selected_angle is not None:
            self._ensure_segment_angles(group)
            group.angles[-1] = dialog.selected_angle
        self._compact_free_angles(group)
        self._refresh_groups()
        self._select_group_by_name(group.name)
        self.dirty = True
        self.canvas.update()
        self.status_bar.showMessage(f"Segment {start} → {end} added to '{group.name}'.")

    def _rotate_selected_group(self):
        """Rotate every group landmark around the first segment's start point."""

        group_name = self._selected_group_name()
        if group_name is None:
            QMessageBox.warning(self, "Group rotation", "Select an ordinary group first.")
            return
        group = self.groups[group_name]
        if not group.segments:
            QMessageBox.warning(
                self, "Group rotation", "The selected group has no segments."
            )
            return
        try:
            angle = float(self.group_rotation_edit.text())
        except ValueError:
            QMessageBox.warning(
                self, "Group rotation", "Enter a rotation angle as a number."
            )
            return
        if not math.isfinite(angle):
            QMessageBox.warning(
                self, "Group rotation", "The rotation angle must be finite."
            )
            return

        proximal_name, first_end = group.segments[0]
        proximal_landmark = self.landmarks[proximal_name]
        first_end_landmark = self.landmarks[first_end]
        if not proximal_landmark.is_placed or not first_end_landmark.is_placed:
            QMessageBox.warning(
                self,
                "Group rotation",
                "Place the first segment landmarks before rotating the group.",
            )
            return

        proximal_point = QPointF(proximal_landmark.x, proximal_landmark.y)
        display_pivot = self.canvas.source_to_display.map(proximal_point)
        first_end_display = self.canvas.source_to_display.map(
            QPointF(first_end_landmark.x, first_end_landmark.y)
        )
        radians = math.radians(angle)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        group_landmarks = {
            landmark_name for segment in group.segments for landmark_name in segment
        }
        for landmark_name in group_landmarks:
            landmark = self.landmarks[landmark_name]
            if not landmark.is_placed:
                continue
            display_point = self.canvas.source_to_display.map(
                QPointF(landmark.x, landmark.y)
            )
            dx = display_point.x() - display_pivot.x()
            dy = display_point.y() - display_pivot.y()
            rotated_display = QPointF(
                display_pivot.x() + dx * cosine + dy * sine,
                display_pivot.y() - dx * sine + dy * cosine,
            )
            rotated_point = self.canvas.display_to_source.map(rotated_display)
            landmark.x = rotated_point.x()
            landmark.y = rotated_point.y()

        self._ensure_segment_angles(group)
        first_heading = trigonometric_heading(display_pivot, first_end_display)
        group.angles[0] = normalize_rotation(first_heading + angle - 90)
        self.group_rotation_edit.clear()
        self.dirty = True
        self.canvas.update()
        self.status_bar.showMessage(f"Group '{group.name}' rotated by {angle:g}°.")

    def _delete_group(self):
        name = self._selected_group_name()
        if name is None:
            QMessageBox.warning(self, "Group", "Select a group first.")
            return
        del self.groups[name]
        self._refresh_groups()
        self.dirty = True
        self.canvas.update()

    def _handle_canvas_click(self, image_point: QPointF):
        widget_point = self.canvas.image_to_widget(image_point)
        landmark_name = self.canvas.closest_landmark(widget_point)

        if self.mode == "axis":
            if landmark_name is None:
                self.status_bar.showMessage("Click closer to a placed landmark.")
                return
            if not self.pending_axis_points:
                self.pending_axis_points.append(image_point)
                self.pending_axis_landmark = landmark_name
                self.status_bar.showMessage("Click the other reference axis landmark.")
                self.canvas.update()
                return
            origin = self.pending_axis_points[0]
            if self.pending_axis_landmark == landmark_name:
                QMessageBox.warning(
                    self, "Reference axis", "The two landmarks must be distinct."
                )
                return
            dialog = AxisAlignmentDialog(self)
            if dialog.exec() != QDialog.Accepted:
                self._cancel_definition()
                return
            self.main_axis = MainAxisDefinition(
                self.pending_axis_landmark,
                landmark_name,
                -90 if dialog.alignment == "horizontal" else 0,
            )
            self.canvas.main_axis = self.main_axis
            self._align_main_axis()
            self.pending_axis_points.clear()
            self.pending_axis_landmark = None
            self.mode = "idle"
            self.dirty = True
            self._refresh_axis_landmark_choices()
            self._refresh_groups()
            self.canvas.update()
            self.status_bar.showMessage("Reference axis aligned.")
            return

        if self.mode == "place":
            name = self._selected_landmark_name()
            if name is None:
                return
            landmark = self.landmarks[name]
            landmark.x = image_point.x()
            landmark.y = image_point.y()
            if self.main_axis is not None and name in (
                self.main_axis.start_landmark,
                self.main_axis.end_landmark,
            ):
                self._align_main_axis()
            self.mode = "idle"
            self.dirty = True
            self._refresh_landmarks()
            self._select_landmark_by_name(name)
            self.status_bar.showMessage(f"Landmark '{name}' placed.")
            self.canvas.update()
            return

        if self.mode != "segment":
            return
        if landmark_name is None:
            self.status_bar.showMessage("Click closer to a placed landmark.")
            return
        if self.pending_segment_start is None:
            self.pending_segment_start = landmark_name
            self.status_bar.showMessage(
                f"Segment start '{landmark_name}' selected. Click its destination landmark."
            )
            self.canvas.update()
            return
        if self.pending_segment_start == landmark_name:
            self.status_bar.showMessage(
                "A segment must connect two different landmarks."
            )
            return
        group = self.groups[self.pending_name]
        self._add_segment_with_angle(group, self.pending_segment_start, landmark_name)
        self.pending_segment_start = None
        self.mode = "idle"
        self.canvas.update()

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
        self._refresh_curve_landmark_choices()
        self._refresh_axis_landmark_choices()
        self._refresh_distance_landmark_choices()
        self.canvas.update()

    def _align_main_axis(self):
        """Rotate the image when both reference-axis landmarks are placed."""

        if self.main_axis is None:
            return
        try:
            rotation = proposed_axis_rotation(
                self.main_axis, self.landmarks, self.image_rotation
            )
        except ValueError:
            return
        self.image_rotation = normalize_rotation(self.image_rotation + rotation)
        self.canvas.set_rotation(self.image_rotation)

    def _refresh_curve_landmark_choices(self):
        selected_start = self.curve_start_combo.currentText()
        selected_end = self.curve_end_combo.currentText()
        landmark_names = list(self.landmarks)
        for combo, selected_name in (
            (self.curve_start_combo, selected_start),
            (self.curve_end_combo, selected_end),
        ):
            combo.clear()
            combo.addItems(landmark_names)
            if selected_name in landmark_names:
                combo.setCurrentText(selected_name)

    def _refresh_axis_landmark_choices(self):
        start_landmark = (
            self.main_axis.start_landmark if self.main_axis is not None else ""
        )
        end_landmark = self.main_axis.end_landmark if self.main_axis is not None else ""
        landmark_names = list(self.landmarks)
        for combo, selected_name in (
            (self.axis_start_combo, start_landmark),
            (self.axis_end_combo, end_landmark),
        ):
            combo.clear()
            combo.addItems(landmark_names)
            if selected_name in landmark_names:
                combo.setCurrentText(selected_name)
        alignment = self.main_axis.angle_from_vertical if self.main_axis else 0
        index = self.axis_alignment_combo.findData(alignment)
        self.axis_alignment_combo.setCurrentIndex(max(index, 0))

    def _refresh_distance_landmark_choices(self):
        selected_start = self.distance_start_combo.currentText()
        selected_end = self.distance_end_combo.currentText()
        landmark_names = list(self.landmarks)
        for combo, selected_name in (
            (self.distance_start_combo, selected_start),
            (self.distance_end_combo, selected_end),
        ):
            combo.clear()
            combo.addItems(landmark_names)
            if selected_name in landmark_names:
                combo.setCurrentText(selected_name)

    def _selected_group_name(self) -> str | None:
        item = self.group_list.currentItem()
        name = item.data(Qt.UserRole) if item else None
        return name if name in self.groups else None

    def _select_group_by_name(self, name: str):
        for row in range(self.group_list.count()):
            if self.group_list.item(row).data(Qt.UserRole) == name:
                self.group_list.setCurrentRow(row)
                return

    def _refresh_groups(self):
        selected_item = self.group_list.currentItem()
        selected_name = selected_item.data(Qt.UserRole) if selected_item else None
        self.group_list.clear()
        for group in self.groups.values():
            segments = ", ".join(f"{start} → {end}" for start, end in group.segments)
            self.group_list.addItem(
                f"{group.name}: {segments or 'no segments'}"
            )
            self.group_list.item(self.group_list.count() - 1).setData(
                Qt.UserRole, group.name
            )
        if selected_name:
            self._select_group_by_name(selected_name)

    def _selected_curve_name(self) -> str | None:
        item = self.curve_list.currentItem()
        name = item.data(Qt.UserRole) if item else None
        return name if name in self.curves else None

    def _select_curve_by_name(self, name: str):
        for row in range(self.curve_list.count()):
            if self.curve_list.item(row).data(Qt.UserRole) == name:
                self.curve_list.setCurrentRow(row)
                return

    def _refresh_curves(self):
        selected_name = self._selected_curve_name()
        self.curve_list.clear()
        for curve in self.curves.values():
            self.curve_list.addItem(
                f"{curve.name}: {curve.start_landmark} to {curve.end_landmark} "
                f"({curve.point_count} points)"
            )
            self.curve_list.item(self.curve_list.count() - 1).setData(
                Qt.UserRole, curve.name
            )
        if selected_name:
            self._select_curve_by_name(selected_name)

    def _load_selected_curve(self, current, _previous):
        if current is None:
            return
        name = current.data(Qt.UserRole)
        curve = self.curves.get(name)
        if curve is None:
            return
        self.curve_name_edit.setText(curve.name)
        self.curve_point_count_spin.setValue(curve.point_count)
        self.curve_start_combo.setCurrentText(curve.start_landmark)
        self.curve_end_combo.setCurrentText(curve.end_landmark)

    def _add_curve(self):
        name = self._clean_name(self.curve_name_edit, "Curve", self.curves)
        if name is None:
            return
        start_landmark = self.curve_start_combo.currentText()
        end_landmark = self.curve_end_combo.currentText()
        if not start_landmark or not end_landmark:
            QMessageBox.warning(self, "Curve", "Add two landmarks before defining a curve.")
            return
        if start_landmark == end_landmark:
            QMessageBox.warning(self, "Curve", "Select two different anchor landmarks.")
            return
        self.curves[name] = CurveDefinition(
            name,
            self.curve_point_count_spin.value(),
            start_landmark,
            end_landmark,
        )
        self.curve_name_edit.clear()
        self._refresh_curves()
        self._select_curve_by_name(name)
        self.dirty = True
        self.status_bar.showMessage(f"Curve '{name}' created.")

    def _update_curve(self):
        name = self._selected_curve_name()
        if name is None:
            QMessageBox.warning(self, "Curve", "Select a curve first.")
            return
        start_landmark = self.curve_start_combo.currentText()
        end_landmark = self.curve_end_combo.currentText()
        if not start_landmark or not end_landmark:
            QMessageBox.warning(
                self, "Curve", "Add two landmarks before defining a curve."
            )
            return
        if start_landmark == end_landmark:
            QMessageBox.warning(self, "Curve", "Select two different anchor landmarks.")
            return
        curve = self.curves[name]
        curve.point_count = self.curve_point_count_spin.value()
        curve.start_landmark = start_landmark
        curve.end_landmark = end_landmark
        self._refresh_curves()
        self._select_curve_by_name(name)
        self.dirty = True
        self.status_bar.showMessage(f"Curve '{name}' updated.")

    def _delete_curve(self):
        name = self._selected_curve_name()
        if name is None:
            QMessageBox.warning(self, "Curve", "Select a curve first.")
            return
        del self.curves[name]
        self._refresh_curves()
        self.dirty = True
        self.status_bar.showMessage(f"Curve '{name}' deleted.")

    def _selected_distance_name(self) -> str | None:
        item = self.distance_list.currentItem()
        name = item.data(Qt.UserRole) if item else None
        return name if name in self.distances else None

    def _select_distance_by_name(self, name: str):
        for row in range(self.distance_list.count()):
            if self.distance_list.item(row).data(Qt.UserRole) == name:
                self.distance_list.setCurrentRow(row)
                return

    def _refresh_distances(self):
        selected_name = self._selected_distance_name()
        self.distance_list.clear()
        for name, (start_landmark, end_landmark) in self.distances.items():
            self.distance_list.addItem(f"{name}: {start_landmark} - {end_landmark}")
            self.distance_list.item(self.distance_list.count() - 1).setData(
                Qt.UserRole, name
            )
        if selected_name:
            self._select_distance_by_name(selected_name)

    def _add_distance(self):
        name = self._clean_name(self.distance_name_edit, "Distance", self.distances)
        if name is None:
            return
        start_landmark = self.distance_start_combo.currentText()
        end_landmark = self.distance_end_combo.currentText()
        if not start_landmark or not end_landmark:
            QMessageBox.warning(
                self, "Distance", "Add two landmarks before defining a distance."
            )
            return
        if start_landmark == end_landmark:
            QMessageBox.warning(
                self, "Distance", "Select two different landmarks."
            )
            return
        self.distances[name] = (start_landmark, end_landmark)
        self.distance_name_edit.clear()
        self._refresh_distances()
        self._select_distance_by_name(name)
        self.dirty = True
        self.status_bar.showMessage(f"Distance '{name}' created.")

    def _delete_distance(self):
        name = self._selected_distance_name()
        if name is None:
            QMessageBox.warning(self, "Distance", "Select a distance first.")
            return
        del self.distances[name]
        self._refresh_distances()
        self.dirty = True
        self.status_bar.showMessage(f"Distance '{name}' deleted.")

    def _refresh_lists(self):
        self._refresh_landmarks()
        self._refresh_groups()
        self._refresh_curves()
        self._refresh_distances()
        self.canvas.update()

    def _sync_canvas_data(self):
        self.canvas.landmarks = self.landmarks
        self.canvas.groups = self.groups
        self.canvas.distances = self.distances
        self.canvas.main_axis = self.main_axis
        self.canvas.pending_axis_points = self.pending_axis_points

    def save_json(self):
        if self.image_path is None:
            QMessageBox.warning(self, "Save JSON", "Open an image first.")
            return
        errors = validate_definitions(
            self.landmarks,
            self.groups,
            self.curves,
            self.main_axis,
            self.distances,
        )
        if errors:
            QMessageBox.warning(self, "Save JSON", "\n".join(errors))
            return

        if self.project_path is not None:
            output_path = self.project_path
            try:
                project = load_project(output_path)
                definition_data = json.loads(
                    serialize_json(
                        self.image_path,
                        self.landmarks,
                        self.groups,
                        self.main_axis,
                        self.curves,
                        self.image_rotation,
                        output_path,
                        self.distances,
                    )
                )
                project["definitions"] = definition_data["project_definition"]
                save_project(output_path, project)
            except (OSError, ValueError) as error:
                QMessageBox.critical(self, "Save project", str(error))
                return
            self.output_path = output_path
            self.dirty = False
            self.status_bar.showMessage(f"Saved definitions to {output_path.name}")
            return

        suggested_path = self.output_path or self.image_path.with_suffix(".json")
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save landmark definitions",
            str(suggested_path),
            "JSON files (*.json)",
        )
        if not file_name:
            return
        output_path = pl.Path(file_name)
        if output_path.suffix.lower() != ".json":
            output_path = output_path.with_suffix(".json")
        try:
            output_path.write_text(
                serialize_json(
                    self.image_path,
                    self.landmarks,
                    self.groups,
                    self.main_axis,
                    self.curves,
                    self.image_rotation,
                    output_path,
                    self.distances,
                ),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.critical(self, "Save JSON", str(error))
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
    project_path = pl.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    editor = LandmarkEditor(project_path)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
