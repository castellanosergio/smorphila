from PySide6.QtCore import Qt, QPointF
from PySide6.QtWidgets import QMessageBox

landmarks = {'1': {'coordinates': (1268.3184466019418, 196.70679611650485), 'color': None}, 
             '2': {'coordinates': (1961.196116504855, 212.36504854368934), 'color': None}, 
             '3': {'coordinates': (2015.9999999999998, 545.1029126213592), 'color': None}, 
             '4': {'coordinates': (2340.9087378640775, 545.1029126213592), 'color': None} 
             }

names = ["1", "2", "3", "4"]
punti = []
for name in names:
    dati = landmarks[name]
    punti.append(dati["coordinates"])  # un tuple (x, y)

x, y = punti[0]
puntoQ = QPointF(x,y)
print(puntoQ)



