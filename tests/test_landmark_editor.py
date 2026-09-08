"""Tests for landmark groups and optional segment-angle constraints."""

import os
import pathlib
import tempfile
import tomllib
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFileDialog

from smorphila.landmark_editor import (
    AngleSelectionDialog,
    AngleWheel,
    GroupDefinition,
    ImageCanvas,
    Landmark,
    LandmarkEditor,
    MainAxisDefinition,
    RelativeAngleDiagram,
    angle_choices,
    angle_from_axis,
    deserialize_toml,
    normalize_rotation,
    proposed_axis_rotation,
    serialize_toml,
    trigonometric_heading,
    validate_definitions,
)
from smorphila.plugin_arti import ArtiPlugin


class AngleChoiceTest(unittest.TestCase):
    def test_provides_full_ten_degree_range(self):
        choices = angle_choices(10)

        self.assertEqual(choices[0], -180)
        self.assertEqual(choices[-1], 180)
        self.assertEqual(len(choices), 37)

    def test_provides_full_twenty_degree_range(self):
        choices = angle_choices(20)

        self.assertEqual(choices[0], -180)
        self.assertEqual(choices[-1], 180)
        self.assertEqual(len(choices), 19)


class AngleDiagramTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_first_segment_uses_absolute_angle_wheel(self):
        dialog = AngleSelectionDialog("A → B", 10, None, False)

        self.assertIsInstance(dialog.selector, AngleWheel)
        self.assertNotIsInstance(dialog.selector, RelativeAngleDiagram)
        dialog.close()

    def test_later_segment_uses_relative_turn_diagram(self):
        dialog = AngleSelectionDialog("B → C", 20, -40, True, incoming_angle=35)

        self.assertIsInstance(dialog.selector, RelativeAngleDiagram)
        self.assertEqual(dialog.selector.selected_angle, -40)
        self.assertEqual(dialog.selector.incoming_angle, 35)
        target = QImage(620, 620, QImage.Format_ARGB32)
        dialog.selector.resize(620, 620)
        dialog.selector.render(target)
        self.assertFalse(target.isNull())
        dialog.close()


class MainAxisTest(unittest.TestCase):
    def test_angles_use_trigonometric_orientation(self):
        axis = MainAxisDefinition(QPointF(0, 0), QPointF(1, 0), "horizontal")

        self.assertAlmostEqual(
            trigonometric_heading(QPointF(0, 0), QPointF(0, -1)), 90.0
        )
        self.assertAlmostEqual(
            angle_from_axis(QPointF(0, 0), QPointF(0, -1), axis), 90.0
        )

    def test_proposes_horizontal_rotation(self):
        axis = MainAxisDefinition(QPointF(0, 0), QPointF(0, 10), "horizontal")

        self.assertAlmostEqual(proposed_axis_rotation(axis), -90.0)

    def test_proposes_upward_vertical_rotation(self):
        axis = MainAxisDefinition(QPointF(0, 0), QPointF(10, 0), "vertical")

        self.assertAlmostEqual(proposed_axis_rotation(axis), -90.0)

    def test_accounts_for_current_display_rotation(self):
        axis = MainAxisDefinition(QPointF(0, 0), QPointF(0, 10), "horizontal")

        self.assertAlmostEqual(proposed_axis_rotation(axis, -90), 0.0)
        self.assertEqual(normalize_rotation(270), -90.0)

class ValidationTest(unittest.TestCase):
    def test_reports_unplaced_and_unknown_landmarks(self):
        landmarks = {"A": Landmark("A")}
        groups = {"body": GroupDefinition("body", ["A", "B"], [0.0])}

        errors = validate_definitions(landmarks, groups)

        self.assertIn("Landmark 'A' has not been placed.", errors)
        self.assertIn(
            "Group 'body' references unknown landmark 'B'.", errors
        )

    def test_accepts_numeric_and_free_segment_constraints(self):
        landmarks = {
            "A": Landmark("A", 0, 0),
            "B": Landmark("B", 1, 0),
            "C": Landmark("C", 1, 1),
        }
        groups = {
            "body": GroupDefinition("body", ["A", "B", "C"], [0, None])
        }

        self.assertEqual(validate_definitions(landmarks, groups), [])

    def test_rejects_wrong_constraint_count(self):
        landmarks = {
            "A": Landmark("A", 0, 0),
            "B": Landmark("B", 1, 0),
            "C": Landmark("C", 1, 1),
        }
        groups = {
            "body": GroupDefinition("body", ["A", "B", "C"], [0])
        }

        errors = validate_definitions(landmarks, groups)

        self.assertIn("Group 'body' must have one angle per segment.", errors)


class TomlSerializationTest(unittest.TestCase):
    def setUp(self):
        self.landmarks = {
            "Start": Landmark("Start", 10.5, 20.25),
            "Middle point": Landmark("Middle point", 5, 25),
            "End": Landmark("End", 15, 25),
        }

    def test_serializes_mixed_constraints_for_arti_plugin(self):
        groups = {
            "Head": GroupDefinition(
                "Head", ["Start", "Middle point", "End"], [140.0, None]
            )
        }

        output = serialize_toml(
            pathlib.Path("image example.png"), self.landmarks, groups
        )
        parsed = tomllib.loads(output)

        self.assertEqual(
            parsed["landmarks_groups"]["Head"]["angles"],
            [140.0, "free", 0],
        )

    def test_serializes_independent_oriented_segments(self):
        landmarks = {
            name: Landmark(name, float(index), 0.0)
            for index, name in enumerate(("A", "B", "C", "D"))
        }
        groups = {
            "PAIRINGS": GroupDefinition(
                "PAIRINGS", [("A", "B"), ("C", "D")]
            )
        }

        output = serialize_toml(pathlib.Path("image.png"), landmarks, groups)
        parsed = tomllib.loads(output)

        self.assertEqual(
            parsed["landmarks_groups"]["PAIRINGS"]["segments"],
            [["A", "B"], ["C", "D"]],
        )

    def test_serializes_all_free_segments_as_empty_angles(self):
        groups = {
            "Head": GroupDefinition(
                "Head", ["Start", "Middle point", "End"], []
            )
        }

        output = serialize_toml(
            pathlib.Path("image example.png"), self.landmarks, groups
        )
        parsed = tomllib.loads(output)

        self.assertEqual(parsed["landmarks_groups"]["Head"]["angles"], [])

    def test_round_trips_main_axis_and_image_rotation(self):
        axis = MainAxisDefinition(
            QPointF(12.5, 20), QPointF(100, 40), "vertical"
        )

        output = serialize_toml(
            pathlib.Path("image.png"), self.landmarks, {}, axis, -30
        )
        _, _, loaded_axis, rotation, _ = deserialize_toml(output)

        self.assertEqual(loaded_axis.origin, axis.origin)
        self.assertEqual(loaded_axis.destination, axis.destination)
        self.assertEqual(loaded_axis.alignment, "vertical")
        self.assertEqual(rotation, -30.0)


class TomlDeserializationTest(unittest.TestCase):
    def test_loads_current_mixed_angle_format(self):
        content = """
landmark_names = ["A", "B", "C"]

[landmark_positions.A]
coordinates = [1, 2]
[landmark_positions.B]
coordinates = [3, 4]
[landmark_positions.C]
coordinates = [5, 6]

[landmarks_groups.BODY]
landmarks = ["A", "B", "C"]
angles = [140, "free", 0]
"""

        landmarks, groups, axis, rotation, warnings = deserialize_toml(content)

        self.assertEqual((landmarks["A"].x, landmarks["A"].y), (1.0, 2.0))
        self.assertEqual(groups["BODY"].angles, [140.0, None])
        self.assertIsNone(axis)
        self.assertEqual(rotation, 0.0)
        self.assertEqual(warnings, [])

    def test_loads_legacy_numeric_and_missing_angles(self):
        content = """
landmark_names = ["A", "B", "C"]

[landmark_positions.A]
coordinates = [1, 2]
[landmark_positions.B]
coordinates = [3, 4]

[landmarks_groups.ORIENTED]
landmarks = ["A", "B"]
angles = [90, 0]

[landmarks_groups.FREE]
landmarks = ["B", "C"]
"""

        landmarks, groups, _, _, warnings = deserialize_toml(content)

        self.assertFalse(landmarks["C"].is_placed)
        self.assertEqual(groups["ORIENTED"].angles, [90.0])
        self.assertEqual(groups["FREE"].angles, [])
        self.assertEqual(warnings, [])

    def test_warns_about_legacy_vertex_first_angles(self):
        content = """
landmark_names = ["A", "B"]

[angles.old]
landmarks = ["A", "B", "A"]
degrees = 45

[landmarks_groups.BODY]
landmarks = ["A", "B"]
"""

        _, _, _, _, warnings = deserialize_toml(content)

        self.assertEqual(len(warnings), 1)

    def test_rejects_invalid_toml_without_returning_partial_data(self):
        with self.assertRaisesRegex(ValueError, "Invalid TOML"):
            deserialize_toml("landmark_names = [")


class AutomaticTomlLoadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_open_image_loads_matching_toml(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = pathlib.Path(directory) / "specimen.png"
            image = QImage(20, 20, QImage.Format_RGB32)
            image.fill(0xFFFFFF)
            self.assertTrue(image.save(str(image_path)))
            image_path.with_suffix(".toml").write_text(
                """
landmark_names = ["A", "B"]
[landmark_positions.A]
coordinates = [2, 3]
[landmark_positions.B]
coordinates = [10, 12]
[landmarks_groups.BODY]
landmarks = ["A", "B"]
angles = [20, 0]
""",
                encoding="utf-8",
            )
            editor = LandmarkEditor()

            with patch.object(
                QFileDialog, "getOpenFileName", return_value=(str(image_path), "")
            ):
                editor.open_image()

            self.assertEqual(list(editor.landmarks), ["A", "B"])
            self.assertEqual(editor.groups["BODY"].angles, [20.0])
            self.assertEqual(editor.output_path, image_path.with_suffix(".toml"))
            self.assertFalse(editor.dirty)
            editor.close()

    def test_rotated_canvas_maps_clicks_back_to_source_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = pathlib.Path(directory) / "mapping.png"
            image = QImage(100, 50, QImage.Format_RGB32)
            image.fill(0xFFFFFF)
            self.assertTrue(image.save(str(image_path)))
            canvas = ImageCanvas()
            canvas.resize(600, 500)
            self.assertTrue(canvas.set_image(image_path))
            canvas.set_rotation(90)
            source_point = QPointF(25, 10)

            widget_point = canvas.image_to_widget(source_point)
            mapped_point = canvas.widget_to_image(widget_point)

            self.assertAlmostEqual(mapped_point.x(), source_point.x(), places=6)
            self.assertAlmostEqual(mapped_point.y(), source_point.y(), places=6)

    def test_zoom_preserves_anchor_and_has_safe_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = pathlib.Path(directory) / "zoom.png"
            image = QImage(100, 50, QImage.Format_RGB32)
            image.fill(0xFFFFFF)
            self.assertTrue(image.save(str(image_path)))
            canvas = ImageCanvas()
            canvas.resize(600, 500)
            self.assertTrue(canvas.set_image(image_path))
            anchor = QPointF(330, 270)
            before = canvas.widget_to_image(anchor)

            canvas.zoom_by(2, anchor)
            after = canvas.widget_to_image(anchor)

            self.assertEqual(canvas.zoom_factor, 2.0)
            self.assertIsNotNone(before)
            self.assertIsNotNone(after)
            self.assertAlmostEqual(after.x(), before.x(), places=6)
            self.assertAlmostEqual(after.y(), before.y(), places=6)
            canvas.zoom_by(1000)
            self.assertEqual(canvas.zoom_factor, 20.0)
            canvas.zoom_by(0.0001)
            self.assertEqual(canvas.zoom_factor, 0.25)
            canvas.reset_zoom()
            self.assertEqual(canvas.zoom_factor, 1.0)

    def test_view_menu_controls_zoom(self):
        editor = LandmarkEditor()
        editor._zoom_in()
        self.assertEqual(editor.canvas.zoom_factor, 1.0)
        self.assertEqual(editor.zoom_in_action.text(), "Zoom in")
        self.assertEqual(editor.zoom_out_action.text(), "Zoom out")
        self.assertEqual(editor.fit_image_action.text(), "Fit image")
        editor.close()

    def test_editor_applies_suggested_horizontal_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = pathlib.Path(directory) / "axis.png"
            image = QImage(100, 50, QImage.Format_RGB32)
            image.fill(0xFFFFFF)
            self.assertTrue(image.save(str(image_path)))
            editor = LandmarkEditor()
            self.assertTrue(editor.canvas.set_image(image_path))
            editor._set_editor_enabled(True)
            editor._start_axis_definition()
            editor._handle_canvas_click(QPointF(20, 10))
            editor._handle_canvas_click(QPointF(20, 40))

            editor._apply_axis_rotation()

            self.assertAlmostEqual(editor.image_rotation, -90.0)
            origin = editor.canvas.source_to_display.map(editor.main_axis.origin)
            destination = editor.canvas.source_to_display.map(
                editor.main_axis.destination
            )
            self.assertAlmostEqual(origin.y(), destination.y(), places=6)
            editor.dirty = False
            editor.close()


class ArtiPluginFreeAngleTest(unittest.TestCase):
    @staticmethod
    def _plugin(points):
        class Viewer:
            landmarks = {
                name: {"coordinates": point}
                for name, point in zip(["A", "B", "C"], points)
            }

        return ArtiPlugin(Viewer())

    def test_free_turn_preserves_original_relative_turn(self):
        points = [(0, 0), (1, 0), (1, 1)]
        plugin = self._plugin(points)

        result = plugin.ricalcola_spezzata_orientata(
            ["A", "B", "C"], points, [90, "free", 0]
        )

        self.assertAlmostEqual(result[1][0], 0.0, places=7)
        self.assertAlmostEqual(result[1][1], 1.0, places=7)
        self.assertAlmostEqual(result[2][0], -1.0, places=7)
        self.assertAlmostEqual(result[2][1], 1.0, places=7)

    def test_existing_numeric_angles_keep_their_behavior(self):
        points = [(0, 0), (1, 0), (1, 1)]
        plugin = self._plugin(points)

        result = plugin.ricalcola_spezzata_orientata(
            ["A", "B", "C"], points, [180, 90, 0]
        )

        self.assertAlmostEqual(result[1][0], -1.0, places=7)
        self.assertAlmostEqual(result[1][1], 0.0, places=7)
        self.assertAlmostEqual(result[2][0], -1.0, places=7)
        self.assertAlmostEqual(result[2][1], -1.0, places=7)


if __name__ == "__main__":
    unittest.main()
