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

def optimize_gcode(gcode_lines):
    """
    Optimizes a list of G-code lines by merging consecutive G1 moves
    that share the same Y, Z, and feed rate values.

    UPDATED:
    When a new G1 command is encountered with a different Y, Z, or F,
    the buffered move is flushed and the new command is output immediately,
    rather than being buffered for merging. This prevents an unwanted diagonal
    move when there is an abrupt change in cutting depth.
    """
    optimized_lines = []
    buffer_line = None
    last_cmd_type = None

    def flush_buffer():
        nonlocal buffer_line
        if buffer_line is not None:
            bx, by, bz, bf = buffer_line
            if bf is not None:
                optimized_lines.append(f"G1 X{bx:.3f} Y{by:.3f} Z{bz:.3f} F{bf:.0f}")
            else:
                optimized_lines.append(f"G1 X{bx:.3f} Y{by:.3f} Z{bz:.3f}")
            buffer_line = None

    for line in gcode_lines:
        stripped = line.strip()
        if stripped.startswith("G1"):
            tokens = stripped.split()
            x = y = z = f = None
            for token in tokens:
                if token.startswith("X"):
                    x = float(token[1:])
                elif token.startswith("Y"):
                    y = float(token[1:])
                elif token.startswith("Z"):
                    z = float(token[1:])
                elif token.startswith("F"):
                    f = float(token[1:])

            if last_cmd_type == "G0":
                flush_buffer()
                optimized_lines.append(stripped)
                buffer_line = None
                last_cmd_type = "G1"
                continue

            if buffer_line is None:
                # Start a new merge group.
                buffer_line = (x, y, z, f)
            else:
                bx, by, bz, bf = buffer_line
                # If Y, Z, or F have changed, flush the buffer and output the new command directly.
                if (by != y) or (bz != z) or (bf != f):
                    flush_buffer()
                    optimized_lines.append(stripped)
                    # Do not buffer this command; start fresh on the next one.
                    last_cmd_type = "G1"
                    continue
                else:
                    # Only X has changed; merge by updating the buffered X.
                    buffer_line = (x, by, bz, bf)

            last_cmd_type = "G1"

        elif stripped.startswith("G0"):
            flush_buffer()
            buffer_line = None
            optimized_lines.append(stripped)
            last_cmd_type = "G0"

        else:
            flush_buffer()
            buffer_line = None
            optimized_lines.append(stripped)
            last_cmd_type = None

    flush_buffer()
    return "\n".join(optimized_lines)
