from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QMessageBox, QInputDialog
from PySide6.QtGui import QColor
import math

class SpezzataAligner:
    def __init__(self, viewer):
        self.viewer = viewer
        self.points = []
        self.active = False
        self.show_all_points = True
        

    def start(self):
        self.points = []
        self.active = True
        self.viewer.disattiva_zoom()
        self.viewer.image.setCursor(Qt.CrossCursor)
        self.viewer.selection_mode = False
    
    def handle_click(self, pos: QPointF):
        self.points.append(pos)
        self.draw_preview()

    def handle_double_click(self):
        if len(self.points) < 2:
            QMessageBox.warning(self.viewer, "Error", "Enter at least two points.")
            return
        aligned = self.straighten_polyline(self.points)

        # Chiedi se mostrare tutti i punti o solo primo/ultimo
        scelta = QMessageBox.question(
            self.viewer, "Show points",
            "Do you want to display all points in the polyline?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        self.show_all_points = (scelta == QMessageBox.Yes)

        if not self.show_all_points and len(aligned) > 2:
            aligned = [aligned[0], aligned[-1]]

        self.points = aligned  # mantieni solo quelli allineati
        self.active = False
        self.viewer.image.setCursor(Qt.OpenHandCursor)

        # Disegna su layer
        self.draw_on_layer()
        

    def straighten_polyline(self, points, direction_angle):
        if len(points) < 2:
            return points[:]
        
        dx = self.points[2].x() - self.points[1].x()
        dy = self.points[2].y() - self.points[1].y()
        angolo_con_asse = math.atan2(dy, dx)
        direction_angle = self.determina_direzione_allineamento(angolo_con_asse)
        
        distances = [
            math.hypot(points[i+1].x() - points[i].x(), points[i+1].y() - points[i].y())
            for i in range(len(points)-1)
        ]

        dx = math.cos(direction_angle)
        dy = math.sin(direction_angle)

        aligned_points = [points[0]]
        current_pos = points[0]

        for d in distances:
            next_point = QPointF(current_pos.x() + d * dx, current_pos.y() + d * dy)
            aligned_points.append(next_point)
            current_pos = next_point

        return aligned_points

    def draw_preview(self):
        """Mostra in tempo reale i punti cliccati su layer"""
        self.viewer.layer_manager.clear_layer("spezzata")
        self.viewer.layer_manager.draw_points("spezzata", self.points, color=QColor(255, 255, 255, 150))

    def draw_on_layer(self):
        """Disegna la spezzata finale su un layer """
        if len(self.points) < 2:
            return
        self.viewer.layer_manager.clear_layer("spezzata")
        self.viewer.layer_manager.draw_points("spezzata", self.points, color=Qt.green)

    def determina_direzione_allineamento(self, angolo_rad):
        # Converti l'angolo in gradi
        angolo_gradi = math.degrees(angolo_rad)

        # Porta l'angolo nel range [0, 360)
        angolo_normalizzato = angolo_gradi % 360

        # Determina la direzione secondo le soglie definite
        if -45 <= angolo_gradi < 45 or angolo_normalizzato < 45 or angolo_normalizzato >= 315:
            return 0  # Orizzontale (est)
        elif 45 <= angolo_normalizzato < 135:
            return 90  # Verticale (nord)
        elif 135 <= angolo_normalizzato < 225:
            return 180  # Orizzontale opposta (ovest)
        elif 225 <= angolo_normalizzato < 315:
            return 270  # Verticale opposta (sud)
        
