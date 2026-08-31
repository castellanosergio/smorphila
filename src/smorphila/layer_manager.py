from PySide6.QtGui import QPixmap, QPainter, QPen
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor


class LayerManager:
    def __init__(self, viewer):
        self.viewer = viewer  # riferimento all'ImageViewer principale
        self.layers = {}  # dizionario: nome_layer -> QPixmap
        self.visible = {}  # dizionario: nome_layer -> bool

    def create_layer(self, name):
        """Crea un layer trasparente con lo stesso size dell'immagine attuale"""
        if self.viewer.pixmap is None:
            return
        if name not in self.layers:
            size = self.viewer.pixmap.size()
            pixmap = QPixmap(size)
            pixmap.fill(Qt.transparent)
            self.layers[name] = pixmap
            self.visible[name] = True

    def draw_rect(self, name, rect, color=QColor(0, 255, 0, 180), fill=QColor(0, 255, 0, 60)):
        # print("RECT", rect)
        # print("Layers",self.layers[name])
        if name not in self.layers:
            self.create_layer(name)
            self.visible[name] = True
        painter = QPainter(self.layers[name])
        painter.setPen(color)
        painter.setBrush(fill)
        painter.drawRect(rect)
        self.update_display()
        painter.end()

    def draw_points(self, name, points, color=Qt.red):
        points = [QPointF(pt[0], pt[1]) if isinstance(pt, tuple) else pt for pt in points]
        #print(points)
        """Disegna una lista di QPointF su un layer"""
        zoom_factor = self.viewer.pixmap.width() / self.viewer.view_rect.width()
        radius = int(10 / zoom_factor)

        if name not in self.layers:
            self.create_layer(name)
            print("created layer: ", name)

        painter = QPainter(self.layers[name])
        painter.setPen(color)
        painter.setBrush(color)
        for pt in points:
            painter.drawEllipse(pt, radius, radius)
        painter.end()
        self.update_display()

    def draw_lines(self, name, points, color):
        """Disegna una lista di coppie di punti [(p1, p2), ...] su un layer"""
        points = [tuple(point) for point in points]
        # print("NOME del LAYER", name)
        if name not in self.layers:
            self.create_layer(name)
        painter = QPainter(self.layers[name])
        painter.setPen(QPen(color, 6))
        print("POINTS", points)
        segmenti = list(zip(points[:-1], points[1:]))
        print("SEGMENTI", segmenti)
        #print(f"{p1=}")
        for p1, p2 in segmenti:
            if isinstance(p1, tuple):
                p1 = QPointF(p1[0], p1[1])
            if isinstance(p2, tuple):
                p2 = QPointF(p2[0], p2[1])
            #print(f"{p1=}")
            painter.drawLine(p1, p2)
        painter.end()
        self.update_display()

    def toggle_visibility(self, name):
        """Attiva/disattiva la visibilità di un layer"""
        if name in self.visible:
            self.visible[name] = not self.visible[name]
            self.update_display()

    def clear_layer(self, name):
        if name in self.layers:
            self.layers[name].fill(Qt.transparent)
            self.update_display()

    def update_display(self):
        if self.viewer.pixmap is None:
            return

        # Crea una QPixmap vuota per comporre tutto
        composed = QPixmap(self.viewer.pixmap.size())
        composed.fill(Qt.transparent)

        painter = QPainter(composed)

        # Disegna l'immagine di base
        painter.drawPixmap(0, 0, self.viewer.pixmap)

        # Calcola il raggio adattato allo zoom
        zoom_factor = self.viewer.scaled_pixmap.width() / self.viewer.view_rect.width()
        radius = int(5 / zoom_factor)

        # Loop su tutti i layer visibili
        for name, layer in self.layers.items():
            if not self.visible.get(name, True):
                continue

            if name == "landmarks":
                # Disegna i landmark dal dizionario (non dal QPixmap del layer)
                punti = []
                for nome, info in self.viewer.landmarks.items():
                    coord = info.get("coordinates")
                    if coord:
                        punti.append(QPointF(*coord))

                painter.setBrush(QColor(255, 0, 0, 180))
                painter.setPen(Qt.NoPen)
                for pt in punti:
                    painter.drawEllipse(pt, radius, radius)

            elif name == "semilandmarks":
                punti = []
                for nome, info in self.viewer.semilandmarks.items():
                    punti = info.get("coordinates")
                    print(f"points: {punti}")
                    painter.setBrush(QColor(0, 255, 0, 180))
                    painter.setPen(Qt.NoPen)
                    for pt in punti:
                        pt = QPointF(*pt)
                        painter.drawEllipse(pt, radius, radius)

            else:
                # Disegna normalmente il layer (come pixmap)
                painter.drawPixmap(0, 0, layer)

        painter.end()

        # Ritaglia la porzione visibile e scala
        cropped = composed.copy(self.viewer.view_rect)
        scaled = cropped.scaled(self.viewer.scroll_area.viewport().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.viewer.scaled_pixmap = scaled
        self.viewer.image.setPixmap(scaled)

    def export_layer(self, name, path):
        """Esporta il layer come immagine (PNG, ecc.)"""
        if name in self.layers:
            self.layers[name].save(path)

    def delete_layer(self, name):
        """Rimuove completamente il layer dalla memoria"""
        if name in self.layers:
            del self.layers[name]
        if name in self.visible:
            del self.visible[name]
        self.update_display()

    def clear_all_layers(self):
        """Cancella tutti i layer e aggiorna la visualizzazione"""
        print("[LayerManager] clear_all_layers() called")
        self.layers.clear()
        self.visible.clear()
        self.update_display()
