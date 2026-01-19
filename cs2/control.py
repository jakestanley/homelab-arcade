#!/usr/bin/env python3
import argparse
import getpass

from PyQt6.QtWidgets import QApplication

from py.map import Map, LoadMaps
from py.controller import Controller
from py.ui import ManagerDialog


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
