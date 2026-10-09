from PySide6.QtGui import QColor
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QMessageBox
import copy
import math


class ArtiPlugin:
    def __init__(self, viewer):
        self.viewer = viewer
        self.active = False

    def activate(self):
        if not self.viewer.apply_reference_axis_alignment():
            return
        source_landmarks = self.viewer.idealized_source_from_raw()
        self.viewer.idealized_source_landmarks = copy.deepcopy(source_landmarks)
        self.viewer.landmarks = copy.deepcopy(source_landmarks)
        compatibility_error = self._shared_segment_compatibility_error()
        if compatibility_error:
            self.viewer.landmarks = copy.deepcopy(source_landmarks)
            self.active = False
            QMessageBox.warning(self.viewer, "Idealized polyline", compatibility_error)
            return
        self.active = True
        self.viewer.disattiva_zoom()
        self.viewer.image.setCursor(Qt.CrossCursor)
        # self.nomi = self.viewer.landmark_names
        LD_groups = list(self.viewer.landmarks_groups.keys())
        for layer_name in [
            "landmarks_raw",
            "spezzata",
            "axis_definition",
        ]:
            if layer_name in self.viewer.layer_manager.visible:
                self.viewer.layer_manager.visible[layer_name] = False

        self.viewer.layer_manager.clear_layer("spezzata_idealizzata")
        self.viewer.layer_manager.clear_layer("landmarks")
        self.viewer.layer_manager.clear_layer("axis_definition")
        # self.viewer.layer_manager.update_display()

        # print("LANDMARKS", self.viewer.landmarks)
        for gruppo in LD_groups:
            # print("GRUPPO FUNZIONALE", gruppo)
            group_data = self.viewer.landmarks_groups[gruppo]
            segments = group_data.get("segments")
            if segments is not None:
                self._draw_segment_group(group_data, source_landmarks)
                continue
            landmark_names = group_data["landmarks"]
            angoli = group_data["angles"]
            nuova_spezzata = []
            if len(angoli) > 0:
                print(landmark_names, angoli)
                try:
                    punti = self.get_landmark_points_by_names(self.viewer.landmarks, landmark_names)
                    source_points = self.get_landmark_points_by_names(
                        source_landmarks, landmark_names
                    )
                    print("points", punti)
                    nuova_spezzata = self.ricalcola_spezzata_orientata(
                        landmark_names, punti, angoli, source_points
                    )
                except ValueError as e:
                    print("Error:", e)
            else:
                punti = self.get_landmark_points_by_names(self.viewer.landmarks, landmark_names)
                print("LLL", landmark_names)

            # Aggiorna il dizionario dei landmarks
            lista_tuple = [self.viewer.landmarks[k]["coordinates"] for k in landmark_names]
            lista_qpointf = []
            for coor in lista_tuple:
                if coor:
                    lista_qpointf.append(QPointF(coor[0], coor[1]))

            self.viewer.layer_manager.draw_points("spezzata_idealizzata", lista_qpointf, color=QColor(255, 0, 0, 180))

            if len(nuova_spezzata) > 0:
                self.viewer.layer_manager.draw_lines("spezzata_idealizzata", nuova_spezzata, color=QColor(0, 255, 0, 180))
            else:
                self.viewer.layer_manager.draw_lines("spezzata_idealizzata", punti, color=QColor(0, 255, 0, 180))

        length_errors = self.segment_length_errors(source_landmarks)
        if length_errors:
            QMessageBox.warning(
                self.viewer,
                "Idealized polyline",
                "The idealized polyline did not preserve all source segment lengths:\n"
                + "\n".join(length_errors),
            )

    def _draw_segment_group(self, group_data, source_landmarks):
        """Apply the group's imposed angles while preserving segment lengths."""

        segments = group_data.get("segments", [])
        angles = group_data.get("angles", [])
        original_points = {
            name: tuple(data["coordinates"])
            for name, data in source_landmarks.items()
            if data.get("coordinates")
        }
        headings = {}
        for index, segment in enumerate(segments):
            if not isinstance(segment, (list, tuple)) or len(segment) != 2:
                continue
            start, end = segment
            if start not in original_points or end not in original_points:
                continue
            start_point = self.viewer.landmarks[start]["coordinates"]
            source_start = original_points[start]
            source_end = original_points[end]
            length = math.hypot(
                source_end[0] - source_start[0], source_end[1] - source_start[1]
            )
            original_heading = math.degrees(
                math.atan2(
                    -(source_end[1] - source_start[1]),
                    source_end[0] - source_start[0],
                )
            )
            angle = angles[index] if index < len(angles) else None
            incoming_index = next(
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
            elif incoming_index is None or incoming_index not in headings:
                heading = 90 + float(angle)
            else:
                heading = headings[incoming_index] + float(angle)
            radians = math.radians(heading)
            end_point = (
                start_point[0] + length * math.cos(radians),
                start_point[1] - length * math.sin(radians),
            )
            self.viewer.landmarks[end]["coordinates"] = end_point
            headings[index] = heading
            self.viewer.layer_manager.draw_points(
                "spezzata_idealizzata",
                [QPointF(*start_point), QPointF(*end_point)],
                color=QColor(255, 0, 0, 180),
            )
            self.viewer.layer_manager.draw_lines(
                "spezzata_idealizzata",
                [start_point, end_point],
                color=QColor(0, 255, 0, 180),
            )

    def _shared_segment_compatibility_error(self) -> str | None:
        """Report duplicate directed segments with conflicting angle constraints."""

        constraints = {}
        for group_name, group_data in self.viewer.landmarks_groups.items():
            segments = group_data.get("segments")
            if not isinstance(segments, list):
                continue
            angles = group_data.get("angles", [])
            for index, segment in enumerate(segments):
                if not isinstance(segment, (list, tuple)) or len(segment) != 2:
                    continue
                angle = angles[index] if index < len(angles) else None
                key = tuple(segment)
                if key not in constraints:
                    constraints[key] = (angle, group_name)
                    continue
                previous_angle, previous_group = constraints[key]
                if previous_angle != angle:
                    start, end = key
                    return (
                        f"Shared segment '{start} -> {end}' has incompatible angle "
                        f"constraints in groups '{previous_group}' and '{group_name}'."
                    )
        return ""

    def segment_length_errors(self, source_landmarks) -> list[str]:
        """Return source-length discrepancies for every idealized segment."""

        errors = []
        checked_segments = set()
        for group_data in self.viewer.landmarks_groups.values():
            for segment in group_data.get("segments", []):
                if not isinstance(segment, (list, tuple)) or len(segment) != 2:
                    continue
                start, end = segment
                if (start, end) in checked_segments:
                    continue
                checked_segments.add((start, end))
                source_start = source_landmarks.get(start, {}).get("coordinates")
                source_end = source_landmarks.get(end, {}).get("coordinates")
                ideal_start = self.viewer.landmarks.get(start, {}).get("coordinates")
                ideal_end = self.viewer.landmarks.get(end, {}).get("coordinates")
                if not all((source_start, source_end, ideal_start, ideal_end)):
                    continue
                source_length = math.dist(source_start, source_end)
                ideal_length = math.dist(ideal_start, ideal_end)
                tolerance = max(1e-6, source_length * 1e-9)
                if abs(source_length - ideal_length) > tolerance:
                    errors.append(
                        f"{start} -> {end}: {ideal_length:.6f} instead of {source_length:.6f}"
                    )
        return errors

    def get_landmark_points_by_names(self, landmark_dict: dict, names: list[str]) -> list[tuple]:
        missing = [name for name in names if name not in landmark_dict]
        if missing:
            raise ValueError(f"The following names were not found in the landmarks: {missing}")

        punti = []
        for name in names:
            dati = landmark_dict[name]
            if not dati["coordinates"]:
                raise ValueError(f"The landmark '{name}' has no assigned coordinates.")
            punti.append(dati["coordinates"])  # un tuple (x, y)
        return punti

    def ricalcola_spezzata_orientata(
        self,
        landmark_names: list[str],
        punti: list[tuple],
        angoli: list[float | str],
        source_points: list[tuple] | None = None,
    ) -> list[tuple]:
        if len(punti) < 2 or len(punti) != len(angoli):
            raise ValueError("You need n points and n angle entries")
        if source_points is None:
            source_points = punti
        if len(source_points) != len(punti):
            raise ValueError("Source points must match the reconstructed polyline")
        distanze = [
            math.hypot(
                source_points[i + 1][0] - source_points[i][0],
                source_points[i + 1][1] - source_points[i][1],
            )
            for i in range(len(punti) - 1)
        ]
        original_orientations = [
            math.degrees(
                math.atan2(
                    source_points[i + 1][1] - source_points[i][1],
                    source_points[i + 1][0] - source_points[i][0],
                )
            )
            for i in range(len(punti) - 1)
        ]

        nuova_spezzata = [punti[0]]
        angolo_attuale = self._resolve_first_angle(
            angoli[0], original_orientations[0]
        )

        for i in range(len(distanze)):
            dx = distanze[i] * math.cos(math.radians(angolo_attuale))
            dy = distanze[i] * math.sin(math.radians(angolo_attuale))
            ultimo = nuova_spezzata[-1]
            nuovo_punto = (ultimo[0] + dx, ultimo[1] + dy)
            nuova_spezzata.append(nuovo_punto)
            self.viewer.landmarks[landmark_names[i + 1]]["coordinates"] = nuovo_punto

            if i + 1 < len(distanze):
                angolo_attuale += self._resolve_turn(
                    angoli[i + 1],
                    original_orientations[i],
                    original_orientations[i + 1],
                )

        return nuova_spezzata

    @staticmethod
    def _is_free_angle(angle: float | str) -> bool:
        if isinstance(angle, str):
            if angle.lower() == "free":
                return True
            raise ValueError(f"Unknown angle constraint: {angle}")
        return False

    def _resolve_first_angle(
        self, angle: float | str, original_orientation: float
    ) -> float:
        if self._is_free_angle(angle):
            return original_orientation
        return float(angle)

    def _resolve_turn(
        self,
        angle: float | str,
        previous_orientation: float,
        current_orientation: float,
    ) -> float:
        if not self._is_free_angle(angle):
            return float(angle)
        turn = current_orientation - previous_orientation
        return (turn + 180) % 360 - 180
