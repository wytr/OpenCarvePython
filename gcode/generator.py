"""
OpenCarve - Image to Gcode-Converter
Copyright (c) 2025 Martin Winter

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
"""

import numpy as np

class GCodeGenerator:
    def __init__(self, params):
        """
        params is a dictionary containing:
          - max_depth_mm
          - safe_z_mm
          - feed_rate_xy
          - feed_rate_z
          - spindle_speed
          - step_down_mm
          - margin
          - width_mm
          - height_mm
          - subdivisions (optional)
        """
        self.max_depth_mm = params.get("max_depth_mm", 2.0)
        self.safe_z_mm = params.get("safe_z_mm", 2.0)
        self.feed_rate_xy = params.get("feed_rate_xy", 300)
        self.feed_rate_z = params.get("feed_rate_z", 100)
        self.spindle_speed = params.get("spindle_speed", 20000)
        self.step_down_mm = params.get("step_down_mm", 3.0)
        self.margin = params.get("margin", 0.0)
        self.width_mm = params.get("width_mm", 100.0)
        self.height_mm = params.get("height_mm", 100.0)
        self.subdivisions = params.get("subdivisions", 0)

    def convert_image_to_gcode(self, image_array):
        """
        image_array: a 2D numpy array of grayscale values.
        Returns a G-code string.
        """
        rows, cols = image_array.shape
        total_passes = int(np.ceil(self.max_depth_mm / self.step_down_mm)) if self.step_down_mm > 0 else 1

        lines = [
            "G90 ; Use absolute coordinates",
            "G21 ; Units in mm",
            "G54 ; Work coordinate system",
            f"M3 S{self.spindle_speed} ; Spindle ON",
            "G4 P5 ; Dwell for 5 seconds",
            f"G0 Z{self.safe_z_mm} F{self.feed_rate_z}",
            "; Begin raster scan"
        ]

        for pass_i in range(1, total_passes + 1):
            pass_depth = min(pass_i * self.step_down_mm, self.max_depth_mm)
            lines.append(f"; --- Pass {pass_i}/{total_passes}, Depth = {pass_depth} mm ---")
            for y in range(rows):
                # Map y: top row -> height_mm - margin, bottom row -> margin.
                y_mm = self.margin + ((rows - 1 - y) / (rows - 1)) * (self.height_mm - 2 * self.margin)
                lines.append(f"G0 X{self.margin:.3f} Y{y_mm:.3f} F{self.feed_rate_xy}")
                row_points = []
                for x in range(cols):
                    # Map x: leftmost -> margin, rightmost -> width_mm - margin.
                    x_mm = self.margin + (x / (cols - 1)) * (self.width_mm - 2 * self.margin)
                    pixel_val = image_array[y, x]
                    pixel_depth = (255 - pixel_val) / 255.0 * self.max_depth_mm
                    row_points.append((x_mm, min(pixel_depth, pass_depth)))
                # Interpolate between successive pixel positions.
                for i in range(len(row_points) - 1):
                    x0, z0 = row_points[i]
                    x1, z1 = row_points[i + 1]
                    for sub in range(self.subdivisions + 1):
                        t = sub / (self.subdivisions + 1)
                        x_t = x0 + t * (x1 - x0)
                        z_t = z0 + t * (z1 - z0)
                        lines.append(f"G1 X{x_t:.3f} Y{y_mm:.3f} Z-{z_t:.3f} F{self.feed_rate_xy}")
                # Ensure the final pixel in the row is reached.
                final_x, final_z = row_points[-1]
                lines.append(f"G1 X{final_x:.3f} Y{y_mm:.3f} Z-{final_z:.3f} F{self.feed_rate_xy}")
                lines.append(f"G0 Z{self.safe_z_mm} F{self.feed_rate_z}")
        lines.append("M5 ; Spindle OFF")
        lines.append(f"G0 X0 Y0 Z{self.safe_z_mm}")
        return "\n".join(lines)
