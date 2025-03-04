#!/usr/bin/python
# This file is part of OpenCarvePython, written by:
# (C) Martin Winter Email: mwtr@tuta.io
# License: GPL V2 (see LICENSE)
# Original Code can be found at: https://github.com/wytr/OpenCarvePython

from PyQt5 import QtWidgets

def simulate_gcode_time(gcode_str, default_feed_rate=300, rapid_rate=1500.0):
    """
    Simulates the machining time given a G-code string.
    Returns the estimated machining time in minutes.
    """
    lines = gcode_str.split("\n")
    current_feed = None
    last_x = last_y = last_z = None
    total_time = 0.0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("G0") or stripped.startswith("G1"):
            tokens = stripped.split()
            cmd = tokens[0]
            new_x = last_x
            new_y = last_y
            new_z = last_z
            for t in tokens[1:]:
                if t.startswith("X"):
                    new_x = float(t[1:])
                elif t.startswith("Y"):
                    new_y = float(t[1:])
                elif t.startswith("Z"):
                    new_z = float(t[1:])
                elif t.startswith("F"):
                    current_feed = float(t[1:])
            if last_x is None or last_y is None or last_z is None:
                last_x, last_y, last_z = new_x, new_y, new_z
                continue
            dx = (new_x - last_x) if (new_x is not None) else 0
            dy = (new_y - last_y) if (new_y is not None) else 0
            dz = (new_z - last_z) if (new_z is not None) else 0
            dist = (dx ** 2 + dy ** 2 + dz ** 2) ** 0.5
            if cmd == "G0":
                feed_for_move = rapid_rate
            else:
                feed_for_move = current_feed if current_feed else default_feed_rate
            if feed_for_move > 0:
                total_time += dist / feed_for_move
            last_x, last_y, last_z = new_x, new_y, new_z
    return total_time

def show_simulation_result(gcode_str, parent=None):
    total_time = simulate_gcode_time(gcode_str)
    QtWidgets.QMessageBox.information(
        parent,
        "Simulation Result",
        f"Estimated machining time: {total_time:.2f} minutes"
    )
