#!/usr/bin/env python3
import argparse
import getpass
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cs2.py.map import LoadMaps
from cs2.py.controller import Controller
from cs2.py.ui import ManagerDialog


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-H", "--host", type=str, required=True)
    parser.add_argument("-p", "--port", type=str, default=27015)
    return parser.parse_args()


args = get_args()
# password = "blahblahblah"
password = getpass.getpass(f"Enter RCON password for server {args.host}:{args.port}")

maps = LoadMaps()
controller = Controller(args.host, args.port, password)

# app initial setup
app = QApplication([])
ManagerDialog(maps, controller).exec()
