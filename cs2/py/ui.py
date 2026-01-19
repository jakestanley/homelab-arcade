import functools
from typing import List

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, \
    QLabel, QWidget, QDialogButtonBox, QPushButton, QListWidget, \
    QListWidgetItem, QRadioButton, QButtonGroup

from py.map import Map
from py.controller import Controller
from py.modes import MODES


def _ControlPanel() -> QVBoxLayout:
    layout = QVBoxLayout()

    return layout


class MapWidget(QWidget):
    def __init__(self, map: Map, controller: Controller) -> None:
        super().__init__()

        self.map = map

        self.label_name = QLabel(self.map.name)
        self.workshop_button = QPushButton("Workshop")
        self.workshop_button.setEnabled(self.map.workshop)
        self.workshop_button.clicked.connect(self.open_workshop)

        layout = QHBoxLayout()

        layout.addWidget(self.label_name)
        layout.addWidget(self.workshop_button)

        for mode in MODES:
            mode_button = QPushButton(mode.capitalize())
            mode_button.clicked.connect(functools.partial(lambda mode: controller.change_map(self.map, mode), mode))
            layout.addWidget(mode_button)

        self.setLayout(layout)

    def open_workshop(self):
        # Workshop: https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890
        print(f"Opening workshop page for {self.map.name} ({self.map.id})")


class ManagerDialog(QDialog):
    def __init__(self, maps: List[Map], controller: Controller):
        super(ManagerDialog, self).__init__()
        self.setWindowTitle("CS2 Manager")
        self.controller: Controller = controller

        self.setMinimumWidth(1024)
        self.setMinimumHeight(768)

        layout: QVBoxLayout = QVBoxLayout(self)

        # build the game control panel
        cpanel: QHBoxLayout = self.control_panel()

        # build the map list
        self.map_list_widget = QListWidget()
        for map in maps:
            map_widget = MapWidget(map, controller)
            list_item = QListWidgetItem(self.map_list_widget)
            list_item.setSizeHint(map_widget.sizeHint())
            self.map_list_widget.setItemWidget(list_item, map_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)

        # layout ordering
        layout.addLayout(cpanel)
        layout.addWidget(self.map_list_widget)
        layout.addWidget(button_box)

    def control_panel(self):
        layout = QHBoxLayout()

        modes: QVBoxLayout = self.modes_radio()

        restart_button = QPushButton("Restart")
        restart_button.clicked.connect(self.controller.restart)

        layout.addLayout(modes)
        layout.addWidget(QPushButton("Pause"))
        layout.addWidget(restart_button)
        layout.addWidget(QPushButton("Scramble"))

        return layout

    def modes_radio(self):

        layout = QVBoxLayout()

        button_group = QButtonGroup()
        for mode in MODES:
            btn: QRadioButton = QRadioButton(mode)
            layout.addWidget(btn)
            button_group.addButton(btn)

        button_group.buttonClicked.connect(lambda: print)

        return layout
