"""Derive analytical coordinates from the raw image-pixel measurements."""

from __future__ import annotations

import copy
import math


def _coordinates(item):
    if not isinstance(item, dict):
        return None
    coordinates = item.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 2:
        return None
    return float(coordinates[0]), float(coordinates[1])


def _align_point(point, origin, angle):
    x = point[0] - origin[0]
    y = point[1] - origin[1]
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return cosine * x - sine * y, sine * x + cosine * y


def _apply_segment_constraints(landmarks, source_landmarks, group):
    segments = group.get("segments", [])
    angles = group.get("angles", [])
    headings = {}
    for index, segment in enumerate(segments):
        if not isinstance(segment, list) or len(segment) != 2:
            continue
        start, end = segment
        start_point = _coordinates(landmarks.get(start))
        source_start = _coordinates(source_landmarks.get(start))
        source_end = _coordinates(source_landmarks.get(end))
        if start_point is None or source_start is None or source_end is None:
            continue
        length = math.dist(source_start, source_end)
        original_heading = math.degrees(
            math.atan2(
                -(source_end[1] - source_start[1]),
                source_end[0] - source_start[0],
            )
        )
        angle = angles[index] if index < len(angles) else None
        previous = next(
            (
                previous_index
                for previous_index, previous_segment in reversed(
                    list(enumerate(segments[:index]))
                )
                if previous_segment[1] == start
            ),
            None,
        )
        if angle is None or (isinstance(angle, str) and angle.lower() == "free"):
            heading = original_heading
        elif previous is None or previous not in headings:
            heading = 90 + float(angle)
        else:
            heading = headings[previous] + float(angle)
        radians = math.radians(heading)
        landmarks[end]["coordinates"] = (
            start_point[0] + length * math.cos(radians),
            start_point[1] - length * math.sin(radians),
        )
        headings[index] = heading


def _apply_polyline_constraints(landmarks, source_landmarks, group):
    names = group.get("landmarks", [])
    angles = group.get("angles", [])
    points = [_coordinates(landmarks.get(name)) for name in names]
    source_points = [_coordinates(source_landmarks.get(name)) for name in names]
    if (
        len(points) < 2
        or any(point is None for point in points)
        or any(point is None for point in source_points)
    ):
        return
    if len(points) != len(angles):
        return
    lengths = [
        math.dist(source_points[index], source_points[index + 1])
        for index in range(len(points) - 1)
    ]
    orientations = [
        math.degrees(
            math.atan2(
                source_points[index + 1][1] - source_points[index][1],
                source_points[index + 1][0] - source_points[index][0],
            )
        )
        for index in range(len(points) - 1)
    ]
    first_angle = angles[0]
    if first_angle is None or (
        isinstance(first_angle, str) and first_angle.lower() == "free"
    ):
        heading = orientations[0]
    else:
        heading = float(first_angle)
    current = points[0]
    for index, length in enumerate(lengths):
        current = (
            current[0] + length * math.cos(math.radians(heading)),
            current[1] + length * math.sin(math.radians(heading)),
        )
        landmarks[names[index + 1]]["coordinates"] = current
        if index + 1 >= len(lengths):
            continue
        turn = angles[index + 1]
        if turn is None or (isinstance(turn, str) and turn.lower() == "free"):
            delta = (orientations[index + 1] - orientations[index] + 180) % 360 - 180
        else:
            delta = float(turn)
        heading += delta


def idealize_landmarks(raw_landmarks, definitions):
    """Return a constrained landmark geometry derived from immutable raw points."""

    source_landmarks = copy.deepcopy(
        raw_landmarks if isinstance(raw_landmarks, dict) else {}
    )
    landmarks = copy.deepcopy(source_landmarks)
    groups = (
        definitions.get("landmarks_groups", {})
        if isinstance(definitions, dict)
        else {}
    )
    if not isinstance(groups, dict):
        return landmarks
    for group in groups.values():
        if not isinstance(group, dict):
            continue
        if "segments" in group:
            _apply_segment_constraints(landmarks, source_landmarks, group)
        else:
            _apply_polyline_constraints(landmarks, source_landmarks, group)
    return landmarks


def _reference_frame(definitions):
    """Return a validated idealized reference-frame definition or None."""

    if not isinstance(definitions, dict):
        return None
    frame = definitions.get("reference_frame")
    if not isinstance(frame, dict) or frame.get("axis_source") != "idealized":
        return None
    origin = frame.get("origin_landmark")
    axis = frame.get("axis_landmarks")
    if (
        not isinstance(origin, str)
        or not isinstance(axis, list)
        or len(axis) != 2
        or not all(isinstance(name, str) for name in axis)
        or axis[0] == axis[1]
    ):
        return None
    try:
        target_angle = float(frame.get("target_angle_from_vertical", 0))
    except (TypeError, ValueError):
        return None
    return origin, axis[0], axis[1], target_angle


def _idealized_frame_transform(landmarks, frame):
    """Return the origin and rotation from image coordinates to the frame."""

    origin_name, axis_start_name, axis_end_name, target_angle = frame
    origin = _coordinates(landmarks.get(origin_name))
    axis_start = _coordinates(landmarks.get(axis_start_name))
    axis_end = _coordinates(landmarks.get(axis_end_name))
    if origin is None or axis_start is None or axis_end is None:
        return None
    axis_x = axis_end[0] - axis_start[0]
    axis_y = -(axis_end[1] - axis_start[1])
    if math.isclose(axis_x, 0.0) and math.isclose(axis_y, 0.0):
        return None
    axis_heading = math.atan2(axis_y, axis_x)
    target_heading = math.radians(90 + target_angle)
    return origin, target_heading - axis_heading


def _frame_point(point, transform):
    """Map an image point into an origin-centred, y-up analytical frame."""

    origin, angle = transform
    x = point[0] - origin[0]
    y = -(point[1] - origin[1])
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return cosine * x - sine * y, sine * x + cosine * y


def legacy_semilandmarks_to_raw(semilandmarks, transform, offset):
    """Convert legacy analytical semilandmarks to original image pixels."""

    if not isinstance(transform, dict):
        return semilandmarks
    try:
        m11 = float(transform["m11"])
        m12 = float(transform["m12"])
        m21 = float(transform["m21"])
        m22 = float(transform["m22"])
        dx = float(transform["dx"])
        dy = float(transform["dy"])
        offset_x, offset_y = float(offset[0]), float(offset[1])
    except (KeyError, TypeError, ValueError, IndexError):
        return semilandmarks
    determinant = m11 * m22 - m21 * m12
    if determinant == 0:
        return semilandmarks
    raw_semilandmarks = copy.deepcopy(semilandmarks)
    for curve in raw_semilandmarks.values():
        if not isinstance(curve, dict) or not isinstance(curve.get("coordinates"), list):
            continue
        raw_points = []
        for point in curve["coordinates"]:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raw_points.append(point)
                continue
            display_x = float(point[0]) + offset_x - dx
            display_y = float(point[1]) + offset_y - dy
            raw_points.append(
                (
                    (m22 * display_x - m21 * display_y) / determinant,
                    (-m12 * display_x + m11 * display_y) / determinant,
                )
            )
        curve["coordinates"] = raw_points
    return raw_semilandmarks


def derive_coordinates(raw_landmarks, raw_semilandmarks, definitions):
    """Return analytical landmark and semilandmark coordinates for export."""

    landmarks = copy.deepcopy(raw_landmarks if isinstance(raw_landmarks, dict) else {})
    semilandmarks = copy.deepcopy(
        raw_semilandmarks if isinstance(raw_semilandmarks, dict) else {}
    )
    frame = _reference_frame(definitions)
    if frame is not None:
        idealized_landmarks = idealize_landmarks(landmarks, definitions)
        transform = _idealized_frame_transform(idealized_landmarks, frame)
        if transform is None:
            return idealized_landmarks, semilandmarks
        for landmark in idealized_landmarks.values():
            point = _coordinates(landmark)
            if point is not None:
                landmark["coordinates"] = _frame_point(point, transform)
        for curve in semilandmarks.values():
            if not isinstance(curve, dict) or not isinstance(
                curve.get("coordinates"), list
            ):
                continue
            curve["coordinates"] = [
                _frame_point(tuple(point), transform)
                if isinstance(point, (list, tuple)) and len(point) == 2
                else point
                for point in curve["coordinates"]
            ]
        return idealized_landmarks, semilandmarks

    axis = definitions.get("reference_axis") if isinstance(definitions, dict) else None
    names = axis.get("landmarks") if isinstance(axis, dict) else None
    if not isinstance(names, list) or len(names) != 2:
        return landmarks, semilandmarks
    origin = _coordinates(landmarks.get(names[0]))
    target = _coordinates(landmarks.get(names[1]))
    if origin is None or target is None:
        return landmarks, semilandmarks
    angle = math.atan2(-(target[0] - origin[0]), -(target[1] - origin[1]))
    for landmark in landmarks.values():
        point = _coordinates(landmark)
        if point is not None:
            landmark["coordinates"] = _align_point(point, origin, angle)
    for curve in semilandmarks.values():
        if not isinstance(curve, dict) or not isinstance(curve.get("coordinates"), list):
            continue
        curve["coordinates"] = [
            _align_point(tuple(point), origin, angle)
            if isinstance(point, (list, tuple)) and len(point) == 2
            else point
            for point in curve["coordinates"]
        ]
    groups = definitions.get("landmarks_groups", {})
    if isinstance(groups, dict):
        source_landmarks = copy.deepcopy(landmarks)
        for group in groups.values():
            if not isinstance(group, dict):
                continue
            if "segments" in group:
                _apply_segment_constraints(landmarks, source_landmarks, group)
            else:
                _apply_polyline_constraints(landmarks, source_landmarks, group)
    for landmark in landmarks.values():
        point = _coordinates(landmark)
        if point is not None:
            landmark["coordinates"] = (point[0], -point[1])
    for curve in semilandmarks.values():
        if not isinstance(curve, dict) or not isinstance(curve.get("coordinates"), list):
            continue
        curve["coordinates"] = [
            (point[0], -point[1])
            if isinstance(point, (list, tuple)) and len(point) == 2
            else point
            for point in curve["coordinates"]
        ]
    return landmarks, semilandmarks
