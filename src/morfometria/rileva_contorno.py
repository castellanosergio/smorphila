import cv2
import numpy as np
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import QPointF
from math import hypot


class ContourPlugin:
    def __init__(self, viewer):
        self.viewer = viewer
        self.active = True
        self.layer_name = "contours"
        self.color = QColor(0, 255, 255, 180)
        self.nsemilandmarks = 20

    def extract_contours(self):
        
        view_rect = self.viewer.view_rect
        if view_rect is None:
            print("[ContourPlugin] No active selection.")
            return

        cropped = self.viewer.pixmap.copy(view_rect)
        img_cv = self._qpixmap_to_cv2(cropped)
        img_grayscale = cv2.cvtColor(img_cv,cv2.COLOR_BGR2GRAY)
        blurred_img = cv2.medianBlur(img_grayscale, 15)
        _, bw_image = cv2.threshold(blurred_img, 127, 255, cv2.THRESH_BINARY)
        edge_image = cv2.Canny(bw_image, 250, 200)
        contours, _ = cv2.findContours(edge_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        offset_x, offset_y = view_rect.x(), view_rect.y()
        
        contorni_tuples = []

        for contour in contours:
            tuples = []
            lunghezza = 0.0
            last = None
            for pt in contour:
                x = pt[0][0] + offset_x
                y = pt[0][1] + offset_y
                coord = (x, y)
                tuples.append(coord)

                if last is not None:
                    dx = x - last[0]
                    dy = y - last[1]
                    lunghezza += (dx**2 + dy**2)**0.5

                last = coord
            contorni_tuples.append((tuples, lunghezza))

        if contorni_tuples:
            longest = max(contorni_tuples, key=lambda c: c[1])[0]  # prendi solo la lista di punti
        else:
            longest = []            
        
        contorno_spezzato = self.interpolate_line_fixed_number(longest, self.nsemilandmarks)
        self.viewer.layer_manager.clear_layer(self.layer_name)
        self.viewer.layer_manager.draw_lines(self.layer_name, contorno_spezzato, color=self.color)

        self.viewer.layer_manager.update_display()
        
    
    def _qpixmap_to_cv2(self, pixmap):
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
        width, height = image.width(), image.height()
        result = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                color = image.pixelColor(x, y)
                result[y, x] = [color.red(), color.green(), color.blue()]
        return result
    

    def interpolate_line_fixed_number(self, points, n):
        """Restituisce n+1 punti equidistanti lungo la spezzata definita da `points`."""
        if len(points) < 2 or n < 1:
            return [QPointF(x, y) for x, y in points]

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
            p2 = points[i+1]
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

        return new_points

