import sys
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QComboBox, QHBoxLayout, QComboBox, QLineEdit,
    QPushButton, QMessageBox, QGridLayout, QSpacerItem, QSizePolicy, QFileDialog,
    QScrollArea, QMainWindow, QMenuBar, QMenu, QInputDialog
)
from PySide6.QtGui import QAction, QPixmap, QPainter, QColor, QMouseEvent, QTransform, QCursor
from PySide6.QtGui import QMouseEvent, QPainter, QColor, QPixmap
from PySide6.QtCore import Qt, QPoint, QSize, QRect, QEvent, QPointF, QTimer
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut

import glob
import pathlib as pl
import numpy as np

from layer_manager import LayerManager
from plugin_allinea_spezzata import SpezzataAligner
from inserisci_landmarks import LandmarkPlugin
from image_aligner import ImageAligner
from plugin_arti import ArtiPlugin




__version__ = "2025.0"
IMAGE_EXTENSION = "jpg"

class ClickableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewer = parent
        self.setFocusPolicy(Qt.StrongFocus)


    def enterEvent(self, event):
        if self.viewer.inserisci_landmarks.active or self.viewer.spezzata_plugin.active:
            self.setCursor(Qt.CrossCursor)
            QApplication.setOverrideCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ClosedHandCursor)
            QApplication.setOverrideCursor(Qt.ClosedHandCursor)

    
    def leaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)


    def mousePressEvent(self, event):
        if self.viewer.image_aligner.active:
            mapped = self.map_to_pixmap_coordinates(event.position())
            self.viewer.image_aligner.handle_click(mapped)
            return

        elif self.viewer.inserisci_landmarks.active:
            mapped = self.map_to_pixmap_coordinates(event.position())
            name = self.viewer.landmark_combo.currentText()
            print("LANDMARK NAME", name)
            self.viewer.inserisci_landmarks.handle_click(name, mapped)
            self.viewer.setCursor(Qt.CrossCursor)

        elif self.viewer.spezzata_plugin.active:
            if event.type() == QEvent.MouseButtonDblClick:
                self.viewer.spezzata_plugin.handle_double_click()
            else:
                mapped = self.map_to_pixmap_coordinates(event.position())
                self.viewer.spezzata_plugin.handle_click(mapped)
            return
        
        elif not self.viewer.selection_mode and event.button() == Qt.LeftButton:
            self.viewer.drag_start_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)

        elif self.viewer.selection_mode and event.button() == Qt.LeftButton:
            mapped_pos = self.map_to_pixmap_coordinates(event.position())
            self.viewer.start_point = mapped_pos
            self.viewer.end_point = mapped_pos
            self.viewer.selecting = True

            


    def mouseMoveEvent(self, event):

        if self.viewer.selection_mode and self.viewer.selecting:
            mapped_pos = self.map_to_pixmap_coordinates(event.position())
            self.viewer.end_point = mapped_pos

            # Disegna il rettangolo di selezione nel layer
            p1 = QPoint(int(self.viewer.start_point.x()), int(self.viewer.start_point.y()))
            p2 = QPoint(int(self.viewer.end_point.x()), int(self.viewer.end_point.y()))
            top_left = QPoint(min(p1.x(), p2.x()), min(p1.y(), p2.y()))
            bottom_right = QPoint(max(p1.x(), p2.x()), max(p1.y(), p2.y()))
            rect = QRect(top_left, bottom_right)
            self.viewer.layer_manager.clear_layer("zoom_preview")
            self.viewer.layer_manager.draw_rect("zoom_preview", rect)
            self.viewer.layer_manager.update_display()


        elif not self.viewer.selection_mode and event.buttons() == Qt.LeftButton:
            if not hasattr(self.viewer, 'view_rect') or self.viewer.drag_start_pos is None:
                return

            dx = event.position().x() - self.viewer.drag_start_pos.x()
            dy = event.position().y() - self.viewer.drag_start_pos.y()

            # Scala in base al rapporto tra immagine e QLabel
            scale_x = self.viewer.pixmap.width() / self.size().width()
            scale_y = self.viewer.pixmap.height() / self.size().height()
            dx *= scale_x
            dy *= scale_y

            # Crea il nuovo rettangolo traslato
            new_rect = QRect(self.viewer.view_rect)
            new_rect.translate(-int(dx), -int(dy))

            # Blocca il rettangolo entro i bordi dell’immagine
            full_rect = QRect(0, 0, self.viewer.pixmap.width(), self.viewer.pixmap.height())

            # Correzione bordo sinistro
            if new_rect.left() < full_rect.left():
                new_rect.moveLeft(full_rect.left())

            # Correzione bordo destro
            if new_rect.right() > full_rect.right():
                new_rect.moveRight(full_rect.right())

            # Correzione bordo superiore
            if new_rect.top() < full_rect.top():
                new_rect.moveTop(full_rect.top())

            # Correzione bordo inferiore
            if new_rect.bottom() > full_rect.bottom():
                new_rect.moveBottom(full_rect.bottom())

            # Aggiorna view_rect
            self.viewer.view_rect = new_rect

            # Aggiorna immagine visualizzata
            container_size = self.viewer.scroll_area.viewport().size()
            cropped = self.viewer.pixmap.copy(self.viewer.view_rect)
            scaled = cropped.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.viewer.scaled_pixmap = scaled
            self.setPixmap(scaled)

            # Imposta la nuova posizione iniziale per il drag successivo
            self.viewer.drag_start_pos = event.position()

    def mouseReleaseEvent(self, event):
        if self.viewer.selection_mode and event.button() == Qt.LeftButton:
            mapped_pos = self.map_to_pixmap_coordinates(event.position())
            self.viewer.end_point = mapped_pos
            self.viewer.selecting = False

            # Pulisce il layer temporaneo del rettangolo
            self.viewer.layer_manager.clear_layer("zoom_preview")
            self.viewer.layer_manager.update_display()

            # Esegue lo zoom
            self.viewer.zoom_to_selection()
            return

    def map_to_pixmap_coordinates(self, pos):
        pixmap = self.pixmap()
        if not pixmap:
            return pos
        label_size = self.size()
        pixmap_size = pixmap.size()
        offset_x = max(0, (label_size.width() - pixmap_size.width()) // 2)
        offset_y = max(0, (label_size.height() - pixmap_size.height()) // 2)
        mapped_x = pos.x() - offset_x
        mapped_y = pos.y() - offset_y

        # Correggi rispetto alla view_rect (per zoom successivi)
        scale_x = self.viewer.view_rect.width() / self.viewer.scaled_pixmap.width()
        scale_y = self.viewer.view_rect.height() / self.viewer.scaled_pixmap.height()

        corrected_x = self.viewer.view_rect.x() + mapped_x * scale_x
        corrected_y = self.viewer.view_rect.y() + mapped_y * scale_y

        return QPointF(corrected_x, corrected_y)

class ImageViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
       
        self.debug_mode = False

        grid = QGridLayout()
        grid.setSpacing(5)
        self.start_point = None
        self.end_point = None
        self.drag_start_pos = None
        self.selecting = False

        # inizializzo lista landamarks
        self.landmark_names = ["SNOUT", "VENT", 
                          "LHead1", "LHead2", "RHead1", "RHead2",
                          "LArmPit", "LElb", "LMCarp", "LFingerHand", 
                          "RArmPit", "RElb", "RMCarp", "RFingerHand",
                          "LKnee", "LTar", "LToe",
                          "RKnee", "RTar", "RToe"]
        self.landmarks_groups = {'SVL': {"landmarks": ["SNOUT", "VENT"], "angles": []},
                            'HEAD': {"landmarks": ["SNOUT","LHead1", "LHead2", "LArmPit", "RArmPit","RHead2", "RHead1", "SNOUT"], "angles": []}, 
                            "L_FORELIMB": {"landmarks":["LArmPit", "LElb", "LMCarp", "LFingerHand"], "angles":[180, 90, 0, 0]}, 
                            "R_FORELIMB": {"landmarks":["RArmPit", "RElb", "RMCarp", "RFingerHand"],"angles": [0, -90, 0, 0]},
                            "L_HINDLIMB": {"landmarks":["VENT","LKnee", "LTar", "LToe"], "angles": [180, -90, 90, 90]},
                            "R_HINDLIMB": {"landmarks":["VENT","RKnee", "RTar", "RToe"], "angles": [0, 90, -90, -90]} 
                            }

        self.landmarks = self.init_landmarks(self.landmark_names)
        self.scale_factor = 1    
        self.plugin_arti = ArtiPlugin(self)
        self.image = ClickableLabel(self)
        self.image.setAlignment(Qt.AlignCenter)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.image)
        grid.addWidget(self.scroll_area, 0, 0, 6, 10)

        self.selection_mode = False
        self.activate_selector_button = QPushButton("Zoom")
        self.activate_selector_button.setCheckable(True)
        self.activate_selector_button.clicked.connect(self.toggle_selection_mode)
        grid.addWidget(self.activate_selector_button, 8, 5, 1, 1)

        self.landmark_combo = QComboBox()
        self.landmark_combo.addItems(self.landmark_names)
        grid.addWidget(QLabel("Landmarks"), 8,2,1,1)
        grid.addWidget(self.landmark_combo, 8,3,1,1)

        self.scaling_mode = QComboBox(self)
        self.scaling_mode.addItems(["Auto width", "Auto height", "Original size"])
        self.scaling_mode.setCurrentIndex(1)
        grid.addWidget(QLabel("Image scale:"), 8, 0, 1, 1)
        grid.addWidget(self.scaling_mode, 8, 1, 1, 1)

        self.save_data_button = QPushButton("Save data")
        self.save_data_button.clicked.connect(self.save_data)
        grid.addWidget(self.save_data_button, 8, 9, 1, 1)

        self.reset_button = QPushButton("Reset positions")
        self.reset_button.clicked.connect(self.reset)
        grid.addWidget(self.reset_button, 8, 8, 1, 1)

        self.zoom_out_button = QPushButton("Zoom out")
        self.zoom_out_button.clicked.connect(self.reset_view_rect)
        grid.addWidget(self.zoom_out_button, 8, 6, 1, 1)

        self.central_widget.setLayout(grid)
        self.setWindowTitle(f"Morphometric analysis - v. {__version__}")
        self.resize(1000, 700)

        self.menu_bar = QMenuBar(self)
        self.setMenuBar(self.menu_bar)

        file_menu = QMenu("File", self)
        edit_menu = QMenu("Edit", self)
        landmarks_menu = QMenu("Landmarks", self)
        view_menu = QMenu("View", self)

        self.menu_bar.addMenu(file_menu)
        self.menu_bar.addMenu(edit_menu)
        self.menu_bar.addMenu(landmarks_menu)
        self.menu_bar.addMenu(view_menu)

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.load)
        file_menu.addAction(open_action)

        toggle_layer_action = QAction("Show/Hide landmarks", self)
        toggle_layer_action.triggered.connect(lambda: self.layer_manager.toggle_visibility("landmarks"))
        view_menu.addAction(toggle_layer_action)

        # Plugin: layer manager e strumenti
        self.layer_manager = LayerManager(self)
        self.spezzata_plugin = SpezzataAligner(self)
        self.inserisci_landmarks = LandmarkPlugin(self)
        self.image_aligner = ImageAligner(self)


        # Aggiunta plugin al menu Landmarks
        spezzata_action = QAction("Align polyline", self)
        spezzata_action.triggered.connect(self.spezzata_plugin.start)
        landmarks_menu.addAction(spezzata_action)

        arti_action = QAction("Create idealized polyline", self)
        arti_action.triggered.connect(self.plugin_arti.activate)
        landmarks_menu.addAction(arti_action)

        landmarks_action = QAction("Add landmarks", self)
        landmarks_action.triggered.connect(self.inserisci_landmarks.activate)
        landmarks_menu.addAction(landmarks_action)

        # Aggiunta plugin menu Edit
        rotate_action = QAction("Rotate image", self)
        rotate_action.triggered.connect(self.rotate_image_dialog)
        edit_menu.addAction(rotate_action)

        # Aggiunta plugin menu Edit
        align_action = QAction("Align image", self)
        align_action.triggered.connect(self.image_aligner.align_image)
        edit_menu.addAction(align_action)

        # SHORTCUTS

        # Ctrl+L → attiva landmarks
        shortcut_landmark = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut_landmark.activated.connect(self.inserisci_landmarks.activate)

        # Ctrl + "1" → zoom in
        zoom_in_shortcut = QShortcut(QKeySequence("1"), self)
        zoom_in_shortcut.setContext(Qt.ApplicationShortcut)
        zoom_in_shortcut.activated.connect(lambda: print("Zoom 1 activated") or self.zoom_plus(1.1))

        # Ctrl + "-" → zoom out
        shortcut_zoom_out = QShortcut(QKeySequence("0"), self)
        shortcut_zoom_out.activated.connect(lambda: self.zoom_plus(0.9))

        # Esc → disattiva tutto
        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self.disattiva_tutti_i_plugin)

        # Shortcut Frecce
        shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self)
        shortcut_left.activated.connect(lambda: self.move_view_rect(-1,0))

        shortcut_right = QShortcut(QKeySequence(Qt.Key_Right), self)
        shortcut_right.activated.connect(lambda: self.move_view_rect(1, 0))
        
        shortcut_up = QShortcut(QKeySequence(Qt.Key_Up), self)
        shortcut_up.activated.connect(lambda: self.move_view_rect(0, -1))

        shortcut_down = QShortcut(QKeySequence(Qt.Key_Down), self)
        shortcut_down.activated.connect(lambda: self.move_view_rect(0, 1))
        
        # Dai il focus a un widget che può ricevere eventi
        self.central_widget.setFocusPolicy(Qt.StrongFocus)
        self.central_widget.setFocus()


        self.show()
        QTimer.singleShot(500, lambda: print("Initial focus:", self.focusWidget()))
    
    def move_view_rect(self, dx, dy):
        if not hasattr(self, 'view_rect') or self.view_rect is None:
            return
        step = int(self.view_rect.width() * 0.1)
        print("STEP", step)
        dx *= step
        dy *= step  
        # Crea una copia del rettangolo corrente
        new_rect = QRect(self.view_rect)

        # Sposta il rettangolo
        new_rect.translate(dx, dy)

        # Limita il rettangolo ai bordi dell'immagine
        full_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        new_rect = new_rect.intersected(full_rect)

        # Applica il nuovo rettangolo di vista
        self.set_view_rect(new_rect)

        
    def load(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image", "", f"Images (*.{IMAGE_EXTENSION})"
        )
        if not file_path:
            return
        self.glb = [file_path]
        self.idx = 0
        self.load_image(self.glb[self.idx])
        


    def load_image(self, file_name):
        self.reset_all()
        self.pixmap = QPixmap()
        self.pixmap.load(file_name)
        
        self.view_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        mode = self.scaling_mode.currentText()
        screen_geom = self.screen().availableGeometry()
        if mode == "Auto width":
            target_width = int(screen_geom.width() * 0.7)
            scaled_pixmap = self.pixmap.scaledToWidth(target_width, Qt.SmoothTransformation)
        elif mode == "Auto height":
            target_height = int(screen_geom.height() * 0.6)
            scaled_pixmap = self.pixmap.scaledToHeight(target_height, Qt.SmoothTransformation)
        else:
            scaled_pixmap = self.pixmap
        #print(scaled_pixmap)
        self.scaled_pixmap = scaled_pixmap
        
        self.image.setPixmap(scaled_pixmap)
        self.nome_file = pl.Path(file_name).name
        self.DIR_PNG = os.path.dirname(file_name)

        self.layer_manager.create_layer("spezzata")
        self.layer_manager.create_layer("landmarks")
        self.layer_manager.create_layer("zoom_preview")
        #self.layer_manager.update_display()

    def init_landmarks(self, nomi):
        """
        Inizializza la struttura dei landmark con lista di nomi.
        Ogni landmark ha: coordinate=[], color=None
        """
        print("NAMES", nomi)
        self.landmarks = {
            nome: {
                'coordinates': [],
                'color': None
            } for nome in nomi
        }   
        return self.landmarks

    def rotate_image_dialog(self):
        angle, ok = QInputDialog.getDouble(self, "Rotate image", "Angle (degrees):", 0.0, -360.0, 360.0, 1)
        if ok:
            transform = QTransform()
            transform.rotate(angle)
            rotated_pixmap = self.pixmap.transformed(transform, Qt.SmoothTransformation)
            container_size = self.scroll_area.viewport().size()
            scaled_rotated = rotated_pixmap.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.scaled_pixmap = scaled_rotated
            self.pixmap = rotated_pixmap  # aggiorna anche l'originale
            self.image.setPixmap(scaled_rotated)
            self.reset_view_rect()
            self.layer_manager.create_layer("spezzata")
            self.layer_manager.create_layer("landmarks")
            self.layer_manager.create_layer("zoom_preview")
            self.layer_manager.update_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "scaled_pixmap") and self.scaled_pixmap:
            self.layer_manager.update_display()

    def set_view_rect(self, sel_rect):
        # Calcola rapporto container
        container_size = self.scroll_area.viewport().size()
        container_ratio = container_size.width() / container_size.height()
        sel_ratio = sel_rect.width() / sel_rect.height() if sel_rect.height() > 0 else 1
       
        adjusted_rect = QRect(sel_rect)
        if sel_ratio < container_ratio:
            new_width = sel_rect.height() * container_ratio
            dx = int((new_width - sel_rect.width()) / 2)
            adjusted_rect.adjust(-dx, 0, dx, 0)
        else:
            new_height = sel_rect.width() / container_ratio
            dy = int((new_height - sel_rect.height()) / 2)
            adjusted_rect.adjust(0, -dy, 0, dy)

        # Intersezione con l'immagine (limita ai bordi)
        full_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        self.view_rect = adjusted_rect.intersected(full_rect)

        # Mostra la nuova porzione
        cropped = self.pixmap.copy(self.view_rect)
        scaled = cropped.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.scaled_pixmap = scaled

        print("scaled_pixmap", self.scaled_pixmap)
        self.image.setPixmap(scaled)
    
    def zoom_to_selection(self):
        if self.start_point is None or self.end_point is None:
            return
        
        x1, y1 = self.start_point.x(), self.start_point.y()
        x2, y2 = self.end_point.x(), self.end_point.y()

        sel_rect_original = QRect(
            int(min(x1, x2)),
            int(min(y1, y2)),
            int(abs(x2 - x1)),
            int(abs(y2 - y1))
        )

        # Intersezione con i limiti dell'immagine originale
        full_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
        corrected_rect = sel_rect_original.intersected(full_rect)

        print("[zoom_to_selection] final selection:", corrected_rect)
        self.set_view_rect(corrected_rect)
        self.layer_manager.update_display()
        

    def zoom_plus(self, factor):
        if not hasattr(self, 'pixmap') or self.pixmap.isNull():
            print("No image loaded; cannot zoom")
            return

        print(f"[zoom_plus] called with factor = {factor}, scale_factor = {self.scale_factor}")

        # Scrollbar e viewport
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        viewport_size = self.scroll_area.viewport().size()

        # Coordinate centro visibile nella viewport
        cx = h_bar.value() + viewport_size.width() // 2
        cy = v_bar.value() + viewport_size.height() // 2

        # Correggi per margine interno nel QLabel (centraggio)
        label_size = self.image.size()
        pixmap_size = self.scaled_pixmap.size()
        offset_x = max(0, (label_size.width() - pixmap_size.width()) // 2)
        offset_y = max(0, (label_size.height() - pixmap_size.height()) // 2)
        cx -= offset_x
        cy -= offset_y

        # Conversione in coordinate dell'immagine originale
        scale_x = self.view_rect.width() / self.scaled_pixmap.width()
        scale_y = self.view_rect.height() / self.scaled_pixmap.height()
        center_x = self.view_rect.x() + cx * scale_x
        center_y = self.view_rect.y() + cy * scale_y

        # Nuova dimensione desiderata
        new_width = self.view_rect.width() / factor
        new_height = self.view_rect.height() / factor

        # Limiti minimi: impedisci che il rettangolo diventi troppo piccolo
        if factor < 1.0:
            min_rect_width = self.scroll_area.viewport().width() * scale_x
            min_rect_height = self.scroll_area.viewport().height() * scale_y
            new_width = max(new_width, min_rect_width)
            new_height = max(new_height, min_rect_height)

        # Costruzione nuovo rettangolo centrato
        new_x = int(center_x - new_width / 2)
        new_y = int(center_y - new_height / 2)
        new_rect = QRect(new_x, new_y, int(new_width), int(new_height))
        
        self.set_view_rect(new_rect)

        # Imposta nuovo punto di partenza per eventuale drag
        cursor_pos = self.image.mapFromGlobal(QCursor.pos())
        self.drag_start_pos = cursor_pos

        self.layer_manager.update_display()


    def reset_view_rect(self):
        if self.pixmap:
            self.view_rect = QRect(0, 0, self.pixmap.width(), self.pixmap.height())
            container_size = self.scroll_area.viewport().size()
            cropped = self.pixmap.copy(self.view_rect)
            scaled = cropped.scaled(container_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.scaled_pixmap = scaled
            self.image.setPixmap(scaled)
            self.disattiva_zoom()
    '''
    def reset_zoom(self):
        self.reset_view_rect()
        self.disattiva_zoom()
        #self.selection_mode = False
        #self.activate_selector_button.setChecked(False)
    '''

    def disattiva_zoom(self):
        self.selection_mode = False
        self.activate_selector_button.setChecked(False)
        if self.inserisci_landmarks.active or self.spezzata_plugin.active:
            self.image.setCursor(Qt.CrossCursor)
    
    def toggle_selection_mode(self):
        self.selection_mode = self.activate_selector_button.isChecked()
        if self.selection_mode:
            self.inserisci_landmarks.active = False
            self.spezzata_plugin.active = False
            self.image.setCursor(Qt.CrossCursor)
        else:
            self.image.setCursor(Qt.CrossCursor)

    def reset(self):
        self.landmarks = []
        self.layer_manager.update_display()

    def save_data(self):
        self.show_working_message()

    def show_working_message(self):
        QMessageBox.information(self, "Info", "Working in progress")

    def disattiva_tutti_i_plugin(self):
        self.inserisci_landmarks.deactivate()
        self.spezzata_plugin.active = False
        self.image_aligner.active = False
        self.selection_mode = False
        self.activate_selector_button.setChecked(False)

        # Imposta il cursore della QLabel
        self.image.setCursor(Qt.ClosedHandCursor)

        # Imposta anche il cursore globale
        QApplication.setOverrideCursor(Qt.ClosedHandCursor)

    
    def reset_all(self):
        print("[reset_all] Global reset in progress...")

        # Cancella immagine visualizzata
        self.image.clear()
        self.pixmap = None
        self.scaled_pixmap = None
        self.view_rect = QRect()

        # Azzeramento selezione, zoom, drag
        self.start_point = None
        self.end_point = None
        self.drag_start_pos = None
        self.selecting = False
        self.scale_factor = 1

        #  Scrollbar: reset posizione
        self.scroll_area.horizontalScrollBar().setValue(0)
        self.scroll_area.verticalScrollBar().setValue(0)

        #  Reset ComboBox
        self.landmark_combo.setCurrentIndex(0)
        self.scaling_mode.setCurrentIndex(1)

        #  Pulsanti e stati
        self.selection_mode = False
        self.activate_selector_button.setChecked(False)

        #  Layer: cancella tutto
        if self.layer_manager:
            self.layer_manager.clear_all_layers()  # devi implementare clear_all_layers nel layer_manager

        #  Landmarks: azzera struttura
        self.init_landmarks(self.landmark_names)

        #  Disattiva plugin
        self.disattiva_tutti_i_plugin()

        #  Aggiorna display
        self.layer_manager.update_display()

        print("[reset_all] Completed")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = ImageViewer()
    sys.exit(app.exec())
