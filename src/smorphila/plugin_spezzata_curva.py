from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QButtonGroup,
    QRadioButton,
)
from PySide6.QtGui import QColor
import numpy as np
from math import hypot, cos, sin, atan2, pi, degrees


class LandmarkSemilandmarkDialog(QDialog):
    def __init__(self, viewer, default_n=10):
        super().__init__(viewer)
        self.viewer = viewer
        self.setWindowTitle("Select mode")

        layout = QVBoxLayout(self)
        self.radio_group = QButtonGroup(self)
        self.radio_landmarks = QRadioButton("Landmarks")
        self.radio_semilandmarks = QRadioButton("Semilandmarks")
        self.radio_semilandmarks.setChecked(True)

        self.radio_group.addButton(self.radio_landmarks)
        self.radio_group.addButton(self.radio_semilandmarks)

        layout.addWidget(QLabel("Choose mode:"))
        layout.addWidget(self.radio_landmarks)
        layout.addWidget(self.radio_semilandmarks)

        self.landmark_combo = QComboBox()
        self.landmark_combo.addItems(self.viewer.landmark_names)
        layout.addWidget(QLabel("Choose a landmark:"))
        layout.addWidget(self.landmark_combo)

        self.curva_combo = QComboBox()
        self.curva_combo.addItems(self.viewer.semilandmarks.keys())
        layout.addWidget(QLabel("Choose a curve:"))
        layout.addWidget(self.curva_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.radio_landmarks.toggled.connect(self.aggiorna_visibilita)
        self.aggiorna_visibilita()

    def aggiorna_visibilita(self):
        landmark_attivo = self.radio_landmarks.isChecked()
        self.landmark_combo.setEnabled(landmark_attivo)
        self.curva_combo.setEnabled(not landmark_attivo)

    def is_landmark_mode(self):
        return self.radio_landmarks.isChecked()

    def get_selected_landmark(self):
        return self.landmark_combo.currentText()

    def get_selected_curva(self):
        return self.curva_combo.currentText()


class SpezzataCurva:
    def __init__(self, viewer):
        self.viewer = viewer
        self.color_points = QColor(0, 255, 0, 255)
        self.points = []
        self.qpoints = []
        self.active = False
        self.show_all_points = True
        self.layer_name = "landmarks"

    def start(self):
        self.viewer.mode_label.setText("SEMI LANDMARKS MODE")

        self.points = []
        self.qpoints = []
        self.active = True
        self.viewer.disattiva_zoom()
        self.viewer.selection_mode = False
        if self.viewer.inserisci_landmarks.active:
            self.viewer.inserisci_landmarks.deactivate()
        QMessageBox.information(
            self.viewer, "Point entry", "Double-click to finish."
        )

    def handle_click(self, pos: QPointF):
        # converto QPointF in
        self.viewer.image.setCursor(Qt.CrossCursor)
        pos_tupla = (pos.x(), pos.y())
        self.points.append(pos_tupla)
        self.qpoints.append(pos)
        self.draw_preview()

    def handle_double_click(self):
        # self.viewer.layer_manager.layers["preview"] = None
        if len(self.points) < 2:
            QMessageBox.warning(self.viewer, "Error", "Enter at least two points.")
            return

        dialog = LandmarkSemilandmarkDialog(self.viewer, default_n=10)

        if not dialog.exec():
            return

        if dialog.is_landmark_mode():
            name = dialog.get_selected_landmark()
            punti = self.straighten_polyline(self.qpoints)
            self.viewer.landmarks[name]["coordinates"] = (punti[-1].x(), punti[-1].y())
            print("POINT ADDED", self.viewer.landmarks[name]["coordinates"])
            self.viewer.layer_manager.clear_layer(self.layer_name)
            self.viewer.layer_manager.clear_layer(name)
            self.viewer.layer_manager.draw_points(
                name, punti, color=QColor(255, 0, 255, 255)
            )
        else:
            nome_spezzata = dialog.get_selected_curva()
            nsemilandmarks = self.viewer.semilandmarks[nome_spezzata]["nsemilandmarks"][
                0
            ]
            # -- Landmark da semilandmarks dict --
            namelm1, namelm2 = self.viewer.semilandmarks[nome_spezzata]["landmarks"]
            lm1 = self.viewer.landmarks[namelm1]["coordinates"]
            lm2 = self.viewer.landmarks[namelm2]["coordinates"]

            i1 = self.trova_punto_piu_vicino(lm1, self.points)
            i2 = self.trova_punto_piu_vicino(lm2, self.points)
            print("i1", i1, "i2", i2)
            start = min(i1, i2)
            end = max(i1, i2)
            sottocurva = self.points[start : end + 1]
            # salvo i semilandmarks nel dizionario
            # Interpolazione sulla sottocurva
            contorno_spezzato = self.interpolate_line_fixed_number(
                sottocurva, nsemilandmarks
            )
            self.viewer.semilandmarks[nome_spezzata]["coordinates"] = contorno_spezzato
            print("SEGMENTED CONTOUR", contorno_spezzato)
            # trasformo lista di tuple in lista QPointF
            contorno_punti = [QPointF(x, y) for x, y in contorno_spezzato]
            print("CONTOUR POINTS", contorno_punti)
            self.viewer.layer_manager.clear_layer(self.layer_name)
            self.viewer.layer_manager.draw_points(
                self.layer_name, contorno_punti, color=self.color_points
            )
            self.viewer.layer_manager.draw_lines(
                nome_spezzata, contorno_spezzato, color=self.color_points
            )
            self.viewer.layer_manager.update_display()
            print(self.viewer.semilandmarks)
        self.active = False

        self.viewer.mode_label.setText("")

    def draw_preview(self):
        """Mostra in tempo reale i punti cliccati su layer"""
        self.viewer.layer_manager.clear_layer("preview")
        self.viewer.layer_manager.draw_points(
            "preview", self.qpoints, color=QColor(0, 255, 0, 255)
        )

    def trova_punto_piu_vicino(self, punto, contorno):
        # trasformo lista di QPointF in lista di tupla
        # punti_tuple = [(pt.x(), pt.y()) for pt in contorno]
        A = np.array(contorno)
        B = np.ones_like(A) * punto
        diff = A - B
        dist_sq = np.sum(diff**2, axis=1)
        indice = np.argmin(dist_sq)
        return indice

    def interpolate_line_fixed_number(self, points, n):
        """Restituisce n+1 punti equidistanti lungo la spezzata definita da `points`."""
        # Calcola le distanze tra i punti consecutivi
        segmenti = list(zip(points[:-1], points[1:]))
        distanze = [hypot(p2[0] - p1[0], p2[1] - p1[1]) for p1, p2 in segmenti]
        lunghezza_totale = sum(distanze)

        step = lunghezza_totale / n

        new_points = [points[0]]
        i = 0
        acc = 0.0

        while i < len(points) - 1:
            p1 = points[i]
            p2 = points[i + 1]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            d = hypot(dx, dy)

            if d + acc >= step:
                t = (step - acc) / d
                new_x = p1[0] + t * dx
                new_y = p1[1] + t * dy
                new_point = (new_x, new_y)
                new_points.append(new_point)
                points[i] = (new_x, new_y)  # aggiornamento temporaneo
                acc = 0.0
            else:
                acc += d
                i += 1

        if len(new_points) < n + 1:
            new_points.append(points[-1])
        print("NEW POINTS", new_points)
        return new_points

    def straighten_polyline(self, points):
        if len(points) < 2:
            return points[:]

        dx = points[1].x() - points[0].x()
        dy = points[1].y() - points[0].y()
        angolo_con_asse = atan2(dy, dx)
        direction_angle = self.determina_direzione_allineamento(angolo_con_asse)

        distances = [
            hypot(points[i + 1].x() - points[i].x(), points[i + 1].y() - points[i].y())
            for i in range(len(points) - 1)
        ]

        dx = cos(direction_angle)
        dy = sin(direction_angle)

        aligned_points = [points[0]]
        current_pos = points[0]

        for d in distances:
            next_point = QPointF(current_pos.x() + d * dx, current_pos.y() + d * dy)
            aligned_points.append(next_point)
            current_pos = next_point

        return aligned_points

    def determina_direzione_allineamento(self, angolo_rad):
        # Converti l'angolo in gradi
        angolo_gradi = degrees(angolo_rad)

        # Porta l'angolo nel range [0, 360)
        angolo_normalizzato = angolo_gradi % 360

        # Determina la direzione secondo le soglie definite
        if (
            -45 <= angolo_gradi < 45
            or angolo_normalizzato < 45
            or angolo_normalizzato >= 315
        ):
            return 0  # Orizzontale (est)
        elif 45 <= angolo_normalizzato < 135:
            return pi / 2  # Verticale (nord)
        elif 135 <= angolo_normalizzato < 225:
            return pi  # Orizzontale opposta (ovest)
        elif 225 <= angolo_normalizzato < 315:
            return -pi / 2  # Verticale opposta (sud)
