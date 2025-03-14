#!/usr/bin/python
# This file is part of OpenCarvePython, written by:
# (C) Martin Winter Email: mwtr@tuta.io
# License: GPL V2 (see LICENSE)
# Original Code can be found at: https://github.com/wytr/OpenCarvePython

import os
import importlib
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtGui import QSurfaceFormat
from PIL import Image
import numpy as np

from OpenGL.GL import *
from OpenGL.GLU import *

from gcode.viewer import GcodeViewerWidget
from gcode.parser import GcodeParser
from gcode.generator import GCodeGenerator
from gcode.simulator import show_simulation_result
from gcode.postprocessor import optimize_gcode

std_platform = importlib.import_module('platform')

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenCarve")
        self.setWindowIcon(QtGui.QIcon('logo.png'))
        self.resize(1200, 700)

        self._updating_dimensions = False
        self.original_img = None
        self.image_array = None
        self.pixmap = None

        # Create a main splitter with three panels:
        # Left: Controls, Center: 3D Viewer, Right: Generated G-code display.
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.setCentralWidget(self.main_splitter)

        # Left widget: Controls.
        self.left_widget = QtWidgets.QWidget()
        self._setup_controls(self.left_widget)
        self.main_splitter.addWidget(self.left_widget)

        # Center widget: 3D G-code viewer.
        self.gcode_viewer_widget = GcodeViewerWidget()
        self.main_splitter.addWidget(self.gcode_viewer_widget)

        # Right widget: G-code display panel.
        self.gcode_display_widget = QtWidgets.QWidget()
        self._setup_gcode_display(self.gcode_display_widget)
        self.main_splitter.addWidget(self.gcode_display_widget)

        # Initially collapse the G-code display panel.
        # Here, we set the right panel's size to 0.
        self.main_splitter.setSizes([100, 600, 0])

    def _setup_controls(self, widget):
        layout = QtWidgets.QVBoxLayout(widget)
        # BUTTON ROW
        button_layout = QtWidgets.QHBoxLayout()
        
        self.load_button = QtWidgets.QPushButton("Load Image")
        self.load_button.setToolTip("Click to load a grayscale image from your computer")
        self.load_button.clicked.connect(self.load_image)
        button_layout.addWidget(self.load_button)
        
        self.gen_button = QtWidgets.QPushButton("Generate G-Code")
        self.gen_button.setToolTip("Click to generate G-code from the loaded image")
        self.gen_button.clicked.connect(self.generate_gcode)
        self.gen_button.setEnabled(False)
        button_layout.addWidget(self.gen_button)
        layout.addLayout(button_layout)

        # SUBDIV SLIDER
        subdiv_layout = QtWidgets.QHBoxLayout()
        subdiv_label = QtWidgets.QLabel("Subdivisions per Pixel:")
        subdiv_label.setToolTip("More subdivisions smooth transitions between adjacent pixels")
        subdiv_layout.addWidget(subdiv_label)
        self.subdiv_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.subdiv_slider.setRange(0, 10)
        self.subdiv_slider.setValue(0)
        self.subdiv_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.subdiv_slider.setTickInterval(1)
        self.subdiv_slider.setToolTip("Adjust the number of interpolation steps between pixels")
        subdiv_layout.addWidget(self.subdiv_slider)
        layout.addLayout(subdiv_layout)

        # G-CODE PARAMETERS GroupBox
        params_groupbox = QtWidgets.QGroupBox("G-Code Generation Parameters")
        params_layout = QtWidgets.QFormLayout(params_groupbox)

        self.pixel_size_spin = QtWidgets.QDoubleSpinBox()
        self.pixel_size_spin.setRange(0.01, 100.0)
        self.pixel_size_spin.setSingleStep(0.01)
        self.pixel_size_spin.setValue(0.1)
        self.pixel_size_spin.setToolTip("Set the pixel size in mm; determines spacing between toolpaths")
        params_layout.addRow("Pixel Size (mm):", self.pixel_size_spin)

        self.max_depth_spin = QtWidgets.QDoubleSpinBox()
        self.max_depth_spin.setRange(0.0, 100.0)
        self.max_depth_spin.setSingleStep(0.1)
        self.max_depth_spin.setValue(2.0)
        self.max_depth_spin.setToolTip("Maximum cutting depth in mm. Darker areas cut deeper")
        params_layout.addRow("Max Depth (mm):", self.max_depth_spin)

        self.safe_z_spin = QtWidgets.QDoubleSpinBox()
        self.safe_z_spin.setRange(0.0, 100.0)
        self.safe_z_spin.setSingleStep(0.5)
        self.safe_z_spin.setValue(2.0)
        self.safe_z_spin.setToolTip("Safe Z height for rapid moves (non-cutting)")
        params_layout.addRow("Safe Z (mm):", self.safe_z_spin)

        self.feed_rate_xy_spin = QtWidgets.QSpinBox()
        self.feed_rate_xy_spin.setRange(1, 10000)
        self.feed_rate_xy_spin.setSingleStep(50)
        self.feed_rate_xy_spin.setValue(300)
        self.feed_rate_xy_spin.setToolTip("Set the feed rate for horizontal (XY) movements in mm/min")
        params_layout.addRow("Feed Rate XY (mm/min):", self.feed_rate_xy_spin)

        self.feed_rate_z_spin = QtWidgets.QSpinBox()
        self.feed_rate_z_spin.setRange(1, 10000)
        self.feed_rate_z_spin.setSingleStep(25)
        self.feed_rate_z_spin.setValue(100)
        self.feed_rate_z_spin.setToolTip("Set the feed rate for vertical (Z) movements in mm/min")
        params_layout.addRow("Feed Rate Z (mm/min):", self.feed_rate_z_spin)

        self.spindle_speed_spin = QtWidgets.QSpinBox()
        self.spindle_speed_spin.setRange(0, 50000)
        self.spindle_speed_spin.setSingleStep(500)
        self.spindle_speed_spin.setValue(20000)
        self.spindle_speed_spin.setToolTip("Set the spindle speed in RPM")
        params_layout.addRow("Spindle Speed (RPM):", self.spindle_speed_spin)

        self.step_down_spin = QtWidgets.QDoubleSpinBox()
        self.step_down_spin.setRange(0.01, 100.0)
        self.step_down_spin.setSingleStep(0.1)
        self.step_down_spin.setValue(3.0)
        self.step_down_spin.setToolTip("Step-down value (mm): incremental depth per pass")
        params_layout.addRow("Step-Down (mm):", self.step_down_spin)

        self.margin_spin = QtWidgets.QDoubleSpinBox()
        self.margin_spin.setRange(0.0, 100.0)
        self.margin_spin.setSingleStep(0.1)
        self.margin_spin.setValue(0.0)
        self.margin_spin.setToolTip("Boundary margin (mm) to add a safety offset around the work area")
        params_layout.addRow("Boundary Margin (mm):", self.margin_spin)
        layout.addWidget(params_groupbox)

        # TOOLPATH DIMENSIONS GroupBox
        dims_groupbox = QtWidgets.QGroupBox("Toolpath Dimensions (mm)")
        dims_layout = QtWidgets.QFormLayout(dims_groupbox)

        self.width_mm_spin = QtWidgets.QDoubleSpinBox()
        self.width_mm_spin.setRange(0.0, 100000.0)
        self.width_mm_spin.setSingleStep(0.1)
        self.width_mm_spin.setValue(0.0)
        self.width_mm_spin.setEnabled(False)
        self.width_mm_spin.setToolTip("Total width of the generated toolpath in mm")
        dims_layout.addRow("Width (mm):", self.width_mm_spin)

        self.height_mm_spin = QtWidgets.QDoubleSpinBox()
        self.height_mm_spin.setRange(0.0, 100000.0)
        self.height_mm_spin.setSingleStep(0.1)
        self.height_mm_spin.setValue(0.0)
        self.height_mm_spin.setEnabled(False)
        self.height_mm_spin.setToolTip("Total height of the generated toolpath in mm")
        dims_layout.addRow("Height (mm):", self.height_mm_spin)
        layout.addWidget(dims_groupbox)

        # IMAGE DISPLAY
        self.image_label = QtWidgets.QLabel("No image loaded.")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setToolTip("Displays the loaded image")
        layout.addWidget(self.image_label)
        self.image_label.resizeEvent = lambda event: self.update_image_preview()

        # CHECKBOXES
        self.invert_color_button = QtWidgets.QPushButton("Invert Colors")
        self.invert_color_button.setToolTip("Invert the colors of the loaded image")
        self.invert_color_button.setDisabled(True)
        layout.addWidget(self.invert_color_button)
        self.invert_color_button.clicked.connect(self.invert_image)

        self.optimize_checkbox = QtWidgets.QCheckBox("Use postprocessor optimization")
        self.optimize_checkbox.setToolTip("Merge similar G-code commands for a more efficient output")
        layout.addWidget(self.optimize_checkbox)

        self.simulate_checkbox = QtWidgets.QCheckBox("Time Estimation")
        self.simulate_checkbox.setToolTip("Estimate machining time based on the generated G-code")
        layout.addWidget(self.simulate_checkbox)

        # SIGNALS
        self.pixel_size_spin.valueChanged.connect(self.on_pixel_size_changed)
        self.width_mm_spin.valueChanged.connect(self.on_width_changed)
        self.height_mm_spin.valueChanged.connect(self.on_height_changed)


    def _setup_gcode_display(self, widget):
        layout = QtWidgets.QVBoxLayout(widget)
        # Create a read-only text edit to show generated G-code.
        self.gcode_text_edit = QtWidgets.QPlainTextEdit()
        self.gcode_text_edit.setReadOnly(True)
        self.gcode_text_edit.setToolTip("Displays the generated G-code")
        layout.addWidget(self.gcode_text_edit)
        
        # Create a horizontal layout for buttons.
        btn_layout = QtWidgets.QHBoxLayout()
        # Add a "Copy G-code" button.
        self.copy_button = QtWidgets.QPushButton("Copy G-code")
        self.copy_button.setToolTip("Copy the generated G-code to the clipboard")
        self.copy_button.clicked.connect(self.copy_gcode)
        btn_layout.addWidget(self.copy_button)
        
        # Add a "Save G-code" button.
        self.save_button = QtWidgets.QPushButton("Save G-code")
        self.save_button.setToolTip("Save the generated G-code to a file")
        self.save_button.clicked.connect(self.save_gcode)
        btn_layout.addWidget(self.save_button)
        
        layout.addLayout(btn_layout)


    def save_gcode(self):
        # Open a file save dialog and write the G-code to the selected file.
        file_dialog = QtWidgets.QFileDialog()
        file_path, _ = file_dialog.getSaveFileName(
            self,
            "Save G-Code",
            "",
            "G-Code Files (*.nc *.gcode);;All Files (*)"
        )
        if file_path:
            with open(file_path, "w") as f:
                f.write(self.gcode_text_edit.toPlainText())


    def copy_gcode(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.gcode_text_edit.toPlainText())

    def on_pixel_size_changed(self):
        if self.image_array is None or self.image_array.size == 0 or self._updating_dimensions:
            return
        self._updating_dimensions = True
        try:
            pixel_size = self.pixel_size_spin.value()
            rows, cols = self.image_array.shape
            new_width = cols * pixel_size
            new_height = rows * pixel_size
            self.width_mm_spin.setValue(new_width)
            self.height_mm_spin.setValue(new_height)
        finally:
            self._updating_dimensions = False

    def on_width_changed(self):
        if self.image_array is None or self.image_array.size == 0 or self._updating_dimensions:
            return
        self._updating_dimensions = True
        try:
            width_mm = self.width_mm_spin.value()
            rows, cols = self.image_array.shape
            pixel_size = width_mm / cols if cols > 0 else 0.0
            self.pixel_size_spin.setValue(pixel_size)
            new_height = rows * pixel_size
            self.height_mm_spin.setValue(new_height)
        finally:
            self._updating_dimensions = False

    def on_height_changed(self):
        if self.image_array is None or self.image_array.size == 0 or self._updating_dimensions:
            return
        self._updating_dimensions = True
        try:
            height_mm = self.height_mm_spin.value()
            rows, cols = self.image_array.shape
            pixel_size = height_mm / rows if rows > 0 else 0.0
            self.pixel_size_spin.setValue(pixel_size)
            new_width = cols * pixel_size
            self.width_mm_spin.setValue(new_width)
        finally:
            self._updating_dimensions = False

    def load_image(self):
        file_dialog = QtWidgets.QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            "Open Grayscale Image",
            "",
            "Images (*.png *.tif *.bmp *.jpg *.jpeg)"
        )
        if file_path:
            from PIL import Image
            img = Image.open(file_path)
            # Check if the image is 16-bit grayscale
            if img.mode == "I;16":
                # Convert using numpy: scale 16-bit values (0-65535) to 8-bit (0-255)
                arr = np.array(img, dtype=np.uint16)
                arr = (arr // 256).astype(np.uint8)
                img = Image.fromarray(arr, mode="L")
            else:
                img = img.convert("L")
            self.original_img = img
            self.image_array = np.array(self.original_img)

            self.pixmap = QtGui.QPixmap(file_path)
            self.image_label.setPixmap(
                self.pixmap.scaled(self.image_label.size(), QtCore.Qt.KeepAspectRatio)
            )

            self.width_mm_spin.setEnabled(True)
            self.height_mm_spin.setEnabled(True)

            self.on_pixel_size_changed()

            self.gen_button.setEnabled(True)
            self.invert_color_button.setEnabled(True)




    def invert_image(self):
        self.image_array = 255 - self.image_array
        height, width = self.image_array.shape
        qimage = QtGui.QImage(self.image_array.data, width, height, width, QtGui.QImage.Format_Grayscale8)
        qimage = qimage.copy()
        self.pixmap = QtGui.QPixmap.fromImage(qimage)
        self.image_label.setPixmap(self.pixmap.scaled(self.image_label.size(), QtCore.Qt.KeepAspectRatio))
    
    def update_image_preview(self):
        if self.pixmap:
            self.image_label.setPixmap(
                self.pixmap.scaled(self.image_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            )
    
    def generate_gcode(self):
        if self.image_array is None:
            return

        # Gather parameters in a dictionary.
        params = {
            "max_depth_mm": self.max_depth_spin.value(),
            "safe_z_mm": self.safe_z_spin.value(),
            "feed_rate_xy": self.feed_rate_xy_spin.value(),
            "feed_rate_z": self.feed_rate_z_spin.value(),
            "spindle_speed": self.spindle_speed_spin.value(),
            "step_down_mm": self.step_down_spin.value(),
            "margin": self.margin_spin.value(),
            "width_mm": self.width_mm_spin.value(),
            "height_mm": self.height_mm_spin.value(),
            "subdivisions": self.subdiv_slider.value()
        }
        generator = GCodeGenerator(params)
        gcode_str = generator.convert_image_to_gcode(self.image_array)

        if self.optimize_checkbox.isChecked():
            gcode_lines = gcode_str.split("\n")
            gcode_str = optimize_gcode(gcode_lines)

        if self.simulate_checkbox.isChecked():
            show_simulation_result(gcode_str, parent=self)

        from gcode.parser import GcodeParser
        parser = GcodeParser()
        model = parser.parseString(gcode_str)
        segments = model.segments

        if self.gcode_viewer_widget:
            self.gcode_viewer_widget.loadSegments(segments)

        # Update the G-code display panel with the new code.
        self.gcode_text_edit.setPlainText(gcode_str)

        # Retrieve the current splitter sizes and update only the right panel's size.
        sizes = self.main_splitter.sizes()
        if len(sizes) >= 3:
            sizes[-1] = 300  # Set desired width for the G-code panel
            self.main_splitter.setSizes(sizes)


    def simulate_time(self, gcode_str):
        # Not used directly (simulation is handled in the simulator module).
        pass

def main():
    fmt = QSurfaceFormat()
    fmt.setSamples(4)  # 4× MSAA
    QSurfaceFormat.setDefaultFormat(fmt)
    
    import sys, os, importlib
    std_platform = importlib.import_module('platform')
    if std_platform.system() == 'Windows':
        app = QtWidgets.QApplication(sys.argv + ['-platform', 'windows:darkmode=1'])
    else:
        app = QtWidgets.QApplication(sys.argv)
    # Load the stylesheet from a file.
    stylesheet = load_stylesheet("dark.qss")
    if stylesheet:
        app.setStyleSheet(stylesheet)
    else:
        print("No stylesheet applied.")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

def load_stylesheet(path):
    """
    Reads a stylesheet from a file and returns it as a string.
    """
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Stylesheet file not found: {path}")
        return ""
    except Exception as e:
        print(f"Error reading stylesheet file: {e}")
        return ""

if __name__ == "__main__":
    main()
