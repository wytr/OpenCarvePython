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

import math
import re
from io import StringIO

class GcodeModel:
    def __init__(self, parser):
        self.parser = parser
        self.relative = {"X": 0.0, "Y": 0.0, "Z": 0.0, "F": 0.0, "E": 0.0}
        self.offset = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
        self.isRelative = False
        self.segments = []
        self.layers = None
        self.distance = None
        self.extrudate = None
        self.bbox = None

    def do_G1(self, args, type):
        # G0/G1 move
        coords = dict(self.relative)
        for axis in args.keys():
            if axis in coords:
                if self.isRelative:
                    coords[axis] += args[axis]
                else:
                    coords[axis] = args[axis]
            else:
                self.warn("Unknown axis '%s'" % axis)

        absolute = {
            "X": self.offset["X"] + coords["X"],
            "Y": self.offset["Y"] + coords["Y"],
            "Z": self.offset["Z"] + coords["Z"],
            "F": coords["F"],
            "E": self.offset["E"] + coords["E"],
        }
        seg = Segment(type, absolute, self.parser.lineNb, self.parser.line)
        self.addSegment(seg)

        self.relative = coords

    def do_G28(self, args):
        self.warn("G28 unimplemented")

    def do_G92(self, args):
        if not len(args.keys()):
            # G92 with no args => all to 0
            args = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
        for axis in args.keys():
            if axis in self.offset:
                self.offset[axis] += self.relative[axis] - args[axis]
                self.relative[axis] = args[axis]
            else:
                self.warn("Unknown axis '%s'" % axis)

    def setRelative(self, isRelative):
        self.isRelative = isRelative

    def addSegment(self, segment):
        self.segments.append(segment)

    def warn(self, msg):
        self.parser.warn(msg)

    def error(self, msg):
        self.parser.error(msg)

    def classifySegments(self):
        coords = {"X": 0.0, "Y": 0.0, "Z": 0.0, "F": 0.0, "E": 0.0}
        currentLayerIdx = 0
        currentLayerZ = 0

        for seg in self.segments:
            style = "fly"
            if (seg.coords["X"] == coords["X"]) and (seg.coords["Y"] == coords["Y"]) and (seg.coords["E"] != coords["E"]):
                style = "retract" if (seg.coords["E"] < coords["E"]) else "restore"
            if ((seg.coords["X"] != coords["X"]) or (seg.coords["Y"] != coords["Y"])) and (seg.coords["E"] > coords["E"]):
                style = "extrude"
            if (seg.coords["E"] > coords["E"]) and (seg.coords["Z"] != currentLayerZ):
                currentLayerZ = seg.coords["Z"]
                currentLayerIdx += 1

            seg.style = style
            seg.layerIdx = currentLayerIdx
            coords = seg.coords

    def splitLayers(self):
        coords = {"X": 0.0, "Y": 0.0, "Z": 0.0, "F": 0.0, "E": 0.0}
        self.layers = []
        currentLayerIdx = -1

        for seg in self.segments:
            if currentLayerIdx != seg.layerIdx:
                layer = Layer(coords["Z"])
                layer.start = coords
                self.layers.append(layer)
                currentLayerIdx = seg.layerIdx
            layer.segments.append(seg)
            coords = seg.coords

    def calcMetrics(self):
        self.distance = 0
        self.extrudate = 0
        self.bbox = None

        def extend_bbox(bbox, c):
            if bbox is None:
                return BBox(c)
            bbox.extend(c)
            return bbox

        for layer in self.layers:
            coords = layer.start
            layer.distance = 0
            layer.extrudate = 0
            self.bbox = extend_bbox(self.bbox, coords)

            for seg in layer.segments:
                d = (seg.coords["X"] - coords["X"]) ** 2
                d += (seg.coords["Y"] - coords["Y"]) ** 2
                d += (seg.coords["Z"] - coords["Z"]) ** 2
                seg.distance = math.sqrt(d)
                seg.extrudate = seg.coords["E"] - coords["E"]

                layer.distance += seg.distance
                layer.extrudate += seg.extrudate

                coords = seg.coords
                self.bbox = extend_bbox(self.bbox, coords)

            self.distance += layer.distance
            self.extrudate += layer.extrudate

    def postProcess(self):
        self.classifySegments()
        self.splitLayers()
        self.calcMetrics()

    def __str__(self):
        return f"<GcodeModel: segments={len(self.segments)}, layers={len(self.layers)}, distance={self.distance}, extrudate={self.extrudate}, bbox={self.bbox}>"

class Segment:
    def __init__(self, type_, coords, lineNb, line):
        self.type = type_
        self.coords = coords
        self.lineNb = lineNb
        self.line = line
        self.style = None
        self.layerIdx = None
        self.distance = None
        self.extrudate = None

    def __str__(self):
        return (
            f"<Segment: type={self.type}, lineNb={self.lineNb}, style={self.style}, "
            f"layerIdx={self.layerIdx}, distance={self.distance}, extrudate={self.extrudate}>"
        )

class Layer:
    def __init__(self, z):
        self.Z = z
        self.segments = []
        self.distance = None
        self.extrudate = None
        self.start = None

    def __str__(self):
        return f"<Layer: Z={self.Z}, segments={len(self.segments)}, distance={self.distance}, extrudate={self.extrudate}>"

class BBox:
    def __init__(self, coords):
        self.xmin = self.xmax = coords["X"]
        self.ymin = self.ymax = coords["Y"]
        self.zmin = self.zmax = coords["Z"]

    def extend(self, coords):
        self.xmin = min(self.xmin, coords["X"])
        self.xmax = max(self.xmax, coords["X"])
        self.ymin = min(self.ymin, coords["Y"])
        self.ymax = max(self.ymax, coords["Y"])
        self.zmin = min(self.zmin, coords["Z"])
        self.zmax = max(self.zmax, coords["Z"])

    def dx(self):
        return self.xmax - self.xmin

    def dy(self):
        return self.ymax - self.ymin

    def dz(self):
        return self.zmax - self.zmin

    def cx(self):
        return (self.xmax + self.xmin) / 2.0

    def cy(self):
        return (self.ymax + self.ymin) / 2.0

    def cz(self):
        return (self.zmax + self.zmin) / 2.0

    def __str__(self):
        return f"(X:[{self.xmin},{self.xmax}], Y:[{self.ymin},{self.ymax}], Z:[{self.zmin},{self.zmax}])"

class GcodeParser:
    def __init__(self):
        self.model = GcodeModel(self)
        self.lineNb = 0
        self.line = ""

    def parseFile(self, path):
        with open(path, 'r') as f:
            self.lineNb = 0
            for line in f:
                self.lineNb += 1
                self.line = line.rstrip()
                self.parseLine()

        self.model.postProcess()
        return self.model

    def parseString(self, gcode_str):
        """
        Helper function to parse a G-code string (instead of a file).
        """
        self.model = GcodeModel(self)
        s = StringIO(gcode_str)
        self.lineNb = 0
        for line in s:
            self.lineNb += 1
            self.line = line.rstrip()
            self.parseLine()
        self.model.postProcess()
        return self.model

    def parseLine(self):
        # strip comments (round brackets):
        command = re.sub(r"\([^)]*\)", "", self.line)
        # strip anything after ';'
        idx = command.find(';')
        if idx >= 0:
            command = command[0:idx].strip()
        # also remove any unterminated '('
        idx = command.find('(')
        if idx >= 0:
            self.warn("Stripping unterminated round-bracket comment")
            command = command[0:idx].strip()

        comm = command.split(None, 1)
        code = comm[0] if (len(comm) > 0) else None
        args = comm[1] if (len(comm) > 1) else None

        if code:
            method_name = "parse_" + code
            if hasattr(self, method_name):
                getattr(self, method_name)(args)
            else:
                self.warn("Unknown code '%s'" % code)

    def parseArgs(self, args):
        dic = {}
        if args:
            bits = args.split()
            for bit in bits:
                letter = bit[0]
                try:
                    coord = float(bit[1:])
                except ValueError:
                    coord = 1
                dic[letter] = coord
        return dic

    def parse_G0(self, args):
        # treat G0 same as G1 for geometry
        self.parse_G1(args, "G0")

    def parse_G1(self, args, type="G1"):
        self.model.do_G1(self.parseArgs(args), type)

    def parse_G20(self, args):
        self.error("Unsupported & incompatible: G20 (Inches)")

    def parse_G21(self, args):
        # G21: mm => default
        pass

    def parse_G28(self, args):
        self.model.do_G28(self.parseArgs(args))

    def parse_G90(self, args):
        self.model.setRelative(False)

    def parse_G91(self, args):
        self.model.setRelative(True)

    def parse_G92(self, args):
        self.model.do_G92(self.parseArgs(args))

    def warn(self, msg):
        print("[WARN] Line %d: %s (Text:'%s')" % (self.lineNb, msg, self.line))

    def error(self, msg):
        msg_full = "[ERROR] Line %d: %s (Text:'%s')" % (self.lineNb, msg, self.line)
        print(msg_full)
        raise Exception(msg_full)