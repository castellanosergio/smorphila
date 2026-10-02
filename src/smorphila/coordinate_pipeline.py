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


def _apply_segment_constraints(landmarks, group):
    segments = group.get("segments", [])
    angles = group.get("angles", [])
    headings = {}
    for index, segment in enumerate(segments):
        if not isinstance(segment, list) or len(segment) != 2:
            continue
        start, end = segment
        start_point = _coordinates(landmarks.get(start))
        end_point = _coordinates(landmarks.get(end))
        if start_point is None or end_point is None:
            continue
        length = math.dist(start_point, end_point)
        original_heading = math.degrees(
            math.atan2(-(end_point[1] - start_point[1]), end_point[0] - start_point[0])
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


def _apply_polyline_constraints(landmarks, group):
    names = group.get("landmarks", [])
    angles = group.get("angles", [])
    points = [_coordinates(landmarks.get(name)) for name in names]
    if len(points) < 2 or any(point is None for point in points):
        return
    if len(points) != len(angles):
        return
    lengths = [math.dist(points[index], points[index + 1]) for index in range(len(points) - 1)]
    orientations = [
        math.degrees(
            math.atan2(
                points[index + 1][1] - points[index][1],
                points[index + 1][0] - points[index][0],
            )
        )
        for index in range(len(points) - 1)
    ]
    first_angle = angles[0]
    heading = orientations[0] if isinstance(first_angle, str) else float(first_angle)
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
        if isinstance(turn, str) and turn.lower() == "free":
            delta = (orientations[index + 1] - orientations[index] + 180) % 360 - 180
        else:
            delta = float(turn)
        heading += delta


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
        for group in groups.values():
            if not isinstance(group, dict):
                continue
            if "segments" in group:
                _apply_segment_constraints(landmarks, group)
            else:
                _apply_polyline_constraints(landmarks, group)
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
