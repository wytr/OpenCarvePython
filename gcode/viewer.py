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

import sys
import math
import ctypes
import numpy as np

from .parser import *
from PyQt5.QtGui import QSurfaceFormat, QCursor
from PyQt5.QtWidgets import (QApplication, QOpenGLWidget, QWidget, QVBoxLayout, QToolBar, QAction)
from PyQt5.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import *

class GcodeViewer3D(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Hide rapids or not
        self.hideRapids = False

        # Feed lines (G1)
        self.vbo_feed = None
        self.feed_count = 0

        # Rapid lines (G0)
        self.vbo_rapid = None
        self.rapid_count = 0

        # -----------------------------
        #   Camera / Navigation
        # -----------------------------
        self.zoom = 1.0
        self.camera_distance = 150.0
        self.orbit_x = 0.0
        self.orbit_y = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.interaction_mode = None
        self.lastPos = None

        # Orthographic view size
        self.ortho_size = 100
        self.useOrthographic = False

        # Navigation cube size in pixels
        self.navCubeSize = 100

    # -------------------------------------------------------------------------
    #  Public API
    # -------------------------------------------------------------------------
    def setHideRapids(self, hide: bool):
        """
        Toggle whether G0 (rapid) lines are shown or hidden.
        """
        self.hideRapids = hide
        self.update()

    def setOrthographic(self, ortho: bool):
        """
        Switch between orthographic and perspective projection.
        """
        self.useOrthographic = ortho
        # Recompute the projection immediately.
        self.makeCurrent()
        self.updateProjection()
        self.update()

    def loadSegments(self, segments):
        """
        Separate G0 segments (rapids) from G1 (feed), then
        upload them into separate VBOs for drawing.
        """
        rapid_data = []
        feed_data = []

        # Keep track of the "previous endpoint" to form a line
        prev_x = prev_y = prev_z = 0.0

        for seg in segments:
            x2 = seg.coords["X"]
            y2 = seg.coords["Y"]
            z2 = seg.coords["Z"]

            if seg.type == "G0":
                # Yellow for rapid
                color = (1.0, 1.0, 0.0)
                target = rapid_data
            else:
                # Blue for feed
                color = (0.0, 0.0, 1.0)
                target = feed_data

            # Start vertex
            target.extend([prev_x, prev_y, prev_z, color[0], color[1], color[2]])
            # End vertex
            target.extend([x2, y2, z2, color[0], color[1], color[2]])

            # Update previous endpoint
            prev_x, prev_y, prev_z = x2, y2, z2

        # Convert to numpy arrays
        rapid_array = np.array(rapid_data, dtype=np.float32)
        feed_array  = np.array(feed_data,  dtype=np.float32)

        self.rapid_count = len(rapid_array) // 6
        self.feed_count  = len(feed_array)  // 6

        # Upload to VBOs
        self.vbo_rapid = self.uploadToVBO(rapid_array, self.vbo_rapid)
        self.vbo_feed  = self.uploadToVBO(feed_array,  self.vbo_feed)

        self.update()

    # -------------------------------------------------------------------------
    #  Internal Helpers
    # -------------------------------------------------------------------------
    def uploadToVBO(self, vertex_array, old_vbo):
        """
        Creates (or recreates) a VBO for the given vertex_array.
        """
        if old_vbo is not None:
            glDeleteBuffers(1, [old_vbo])

        if vertex_array.size == 0:
            return None

        self.makeCurrent()
        new_vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, new_vbo)
        glBufferData(GL_ARRAY_BUFFER, vertex_array.nbytes, vertex_array, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        return new_vbo

    # -------------------------------------------------------------------------
    #  OpenGL Overrides
    # -------------------------------------------------------------------------
    def initializeGL(self):
        """
        Called once when the OpenGL context is created.
        Here we enable multisampling for anti-aliasing.
        """
        glEnable(GL_DEPTH_TEST)
        
        # Enable MSAA (multisample anti-aliasing).
        glEnable(GL_MULTISAMPLE)

        # Optionally, if you want to rely solely on MSAA,
        # you could disable old-style line smoothing:
        glDisable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_DONT_CARE)

        line_width = 3.0  # Set the line width to 3.0 (you can adjust this value)
        
        glLineWidth(line_width)  # Set the line width

        glClearColor(0.15, 0.15, 0.15, 1.0)

    def resizeGL(self, w, h):
        """
        Called by Qt when the widget is resized.
        """
        glViewport(0, 0, w, h)
        self.updateProjection()

    def paintGL(self):
        """
        Main render callback. Clear the buffers, then draw the scene + nav cube.
        """
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        self.drawMainScene()
        self.drawNavigationCube()

    def updateProjection(self):
        """
        Recompute the projection matrix based on current width/height
        and whether we are in ortho/perspective mode.
        """
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        aspect = w / h

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if self.useOrthographic:
            left   = -self.ortho_size * aspect
            right  =  self.ortho_size * aspect
            bottom = -self.ortho_size
            top    =  self.ortho_size
            near   = -1000
            far    =  1000
            glOrtho(left, right, bottom, top, near, far)
        else:
            gluPerspective(45.0, aspect, 0.1, 10000.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    # -------------------------------------------------------------------------
    #  Scene Drawing
    # -------------------------------------------------------------------------
    def drawMainScene(self):
        """
        Apply camera transforms and then draw axes + lines (rapids, feeds).
        """
        # Camera transforms
        glTranslatef(self.pan_x, self.pan_y, -self.camera_distance * self.zoom)
        glRotatef(self.orbit_y, 1.0, 0.0, 0.0)
        glRotatef(self.orbit_x, 0.0, 1.0, 0.0)

        # Draw axes for reference
        self.drawAxes()

        # Draw rapid lines
        if (not self.hideRapids) and self.vbo_rapid and self.rapid_count > 0:
            self.drawVBO(self.vbo_rapid, self.rapid_count)

        # Draw feed lines
        if self.vbo_feed and self.feed_count > 0:
            self.drawVBO(self.vbo_feed, self.feed_count)

    def drawAxes(self):
        """
        Draws 3 colored lines representing the X, Y, and Z axes with thicker lines.
        """
        axis_length = 50.0

        glBegin(GL_LINES)
        # X axis => red
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(axis_length, 0.0, 0.0)

        # Y axis => green
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, axis_length, 0.0)

        # Z axis => blue
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, axis_length)
        glEnd()


    def drawVBO(self, vbo, count):
        """
        Helper to draw line segments from a VBO: each vertex is (x,y,z, r,g,b).
        """
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)

        stride = 6 * 4  # x,y,z + r,g,b => 6 floats => 24 bytes
        glVertexPointer(3, GL_FLOAT, stride, ctypes.c_void_p(0))
        glColorPointer(3, GL_FLOAT, stride, ctypes.c_void_p(12))
        glDrawArrays(GL_LINES, 0, count)

        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    # -------------------------------------------------------------------------
    #  Navigation Cube
    # -------------------------------------------------------------------------
    def drawNavigationCube(self):
        """
        Renders a small orientation cube in the top-right corner
        in a separate viewport.
        """
        w = self.width()
        h = self.height()
        navSize = self.navCubeSize

        # Save current projection/modelview
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        proj = glGetDoublev(GL_PROJECTION_MATRIX)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        mv = glGetDoublev(GL_MODELVIEW_MATRIX)

        # Set a small viewport in the top-right corner
        glViewport(w - navSize, h - navSize, navSize, navSize)

        # Setup an orthographic projection for the cube
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(-1.5, 1.5, -1.5, 1.5, -2.0, 2.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # Apply the same orbit rotation
        glRotatef(self.orbit_y, 1.0, 0.0, 0.0)
        glRotatef(self.orbit_x, 0.0, 1.0, 0.0)

        # Draw the cube with 6 faces
        self.drawCube()

        # Restore previous ModelView/Projection
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()

        # Restore the main viewport
        glViewport(0, 0, w, h)

    def drawCube(self):
        """
        Draw a 1x1x1 cube at the origin, each face a different color.
        """
        glBegin(GL_QUADS)

        # +X face (right)
        glColor3f(1.0, 0.0, 0.0)  # bright red
        glVertex3f( 0.5,  0.5, -0.5)
        glVertex3f( 0.5,  0.5,  0.5)
        glVertex3f( 0.5, -0.5,  0.5)
        glVertex3f( 0.5, -0.5, -0.5)

        # -X face (left)
        glColor3f(0.5, 0.0, 0.0)
        glVertex3f(-0.5,  0.5,  0.5)
        glVertex3f(-0.5,  0.5, -0.5)
        glVertex3f(-0.5, -0.5, -0.5)
        glVertex3f(-0.5, -0.5,  0.5)

        # +Y face (top)
        glColor3f(0.0, 1.0, 0.0)  # bright green
        glVertex3f(-0.5,  0.5, -0.5)
        glVertex3f( 0.5,  0.5, -0.5)
        glVertex3f( 0.5,  0.5,  0.5)
        glVertex3f(-0.5,  0.5,  0.5)

        # -Y face (bottom)
        glColor3f(0.0, 0.5, 0.0)
        glVertex3f(-0.5, -0.5,  0.5)
        glVertex3f( 0.5, -0.5,  0.5)
        glVertex3f( 0.5, -0.5, -0.5)
        glVertex3f(-0.5, -0.5, -0.5)

        # +Z face (front)
        glColor3f(0.0, 0.0, 1.0)  # bright blue
        glVertex3f( 0.5,  0.5,  0.5)
        glVertex3f(-0.5,  0.5,  0.5)
        glVertex3f(-0.5, -0.5,  0.5)
        glVertex3f( 0.5, -0.5,  0.5)

        # -Z face (back)
        glColor3f(0.0, 0.0, 0.5)
        glVertex3f(-0.5,  0.5, -0.5)
        glVertex3f( 0.5,  0.5, -0.5)
        glVertex3f( 0.5, -0.5, -0.5)
        glVertex3f(-0.5, -0.5, -0.5)

        glEnd()

    # -------------------------------------------------------------------------
    #  Navigation Cube Picking
    # -------------------------------------------------------------------------
    def isInNavCubeArea(self, x, y):
        """
        Returns True if (x, y) is within the nav cube viewport (top-right).
        In Qt coordinate system, y=0 is the top edge.
        """
        w = self.width()
        h = self.height()
        navSize = self.navCubeSize

        # The nav-cube viewport is (w - navSize, 0) to (w, navSize).
        # So if x >= w - navSize and y <= navSize, it's in that region.
        if x >= (w - navSize) and y <= navSize:
            return True
        return False

    def pickNavCubeFace(self, x, y):
        """
        Use gluUnProject on the nav-cube viewport to figure out which face we hit,
        then snap the camera orientation accordingly.
        """
        w = self.width()
        h = self.height()
        navSize = self.navCubeSize

        # Convert (x, y) to nav-cube local coords
        nav_x = x - (w - navSize)
        nav_y = (navSize - 1) - y  # invert Y for OpenGL

        # Setup a small projection for the cube
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(-1.5, 1.5, -1.5, 1.5, -2.0, 2.0)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glRotatef(self.orbit_y, 1.0, 0.0, 0.0)
        glRotatef(self.orbit_x, 0.0, 1.0, 0.0)

        viewport = [0, 0, navSize, navSize]
        proj = glGetDoublev(GL_PROJECTION_MATRIX)
        model = glGetDoublev(GL_MODELVIEW_MATRIX)

        # Near-plane unproject
        winZ = 0.0
        obj_start = gluUnProject(nav_x, nav_y, winZ, model, proj, viewport)

        # Far-plane unproject
        winZ = 1.0
        obj_end = gluUnProject(nav_x, nav_y, winZ, model, proj, viewport)

        # Restore
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

        # Now we have a ray from obj_start to obj_end
        ray_dir = np.subtract(obj_end, obj_start)
        ray_dir = ray_dir / np.linalg.norm(ray_dir)

        # Intersect with the [-0.5, 0.5]^3 cube:
        candidates = []

        def check_plane(axis_idx, sign):
            denom = ray_dir[axis_idx]
            if abs(denom) < 1e-8:
                return (None, None)
            plane_coord = 0.5 * sign
            t = (plane_coord - obj_start[axis_idx]) / denom
            if t < 0.0:
                return (None, None)
            ix = obj_start[0] + t * ray_dir[0]
            iy = obj_start[1] + t * ray_dir[1]
            iz = obj_start[2] + t * ray_dir[2]
            # Check if intersection is within the face bounds
            check_axes = [0, 1, 2]
            check_axes.remove(axis_idx)
            if abs([ix, iy, iz][check_axes[0]]) > 0.5 + 1e-6:
                return (None, None)
            if abs([ix, iy, iz][check_axes[1]]) > 0.5 + 1e-6:
                return (None, None)
            # Face ID
            if axis_idx == 0:
                face_name = 'X+' if sign > 0 else 'X-'
            elif axis_idx == 1:
                face_name = 'Y+' if sign > 0 else 'Y-'
            else:
                face_name = 'Z+' if sign > 0 else 'Z-'
            return (t, face_name)

        for axis_idx in [0, 1, 2]:
            for sgn in [-1, 1]:
                t_int, face_id = check_plane(axis_idx, sgn)
                if t_int is not None:
                    candidates.append((t_int, face_id))

        if not candidates:
            return

        # Pick the face with smallest t
        _, face_hit = min(candidates, key=lambda x: x[0])
        self.snapToFace(face_hit)

    def snapToFace(self, face):
        """
        Based on which face we clicked ("X+", "X-", "Y+", "Y-", "Z+", "Z-"),
        set orbit_x / orbit_y to a known orientation.
        """
        if face == 'X+':
            self.orbit_x = 90
            self.orbit_y = 0
        elif face == 'X-':
            self.orbit_x = -90
            self.orbit_y = 0
        elif face == 'Y+':
            self.orbit_x = 0
            self.orbit_y = -90
        elif face == 'Y-':
            self.orbit_x = 0
            self.orbit_y = 90
        elif face == 'Z+':
            self.orbit_x = 0
            self.orbit_y = 0
        elif face == 'Z-':
            self.orbit_x = 180
            self.orbit_y = 0

    # -------------------------------------------------------------------------
    #  Mouse Interaction
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event):
        self.lastPos = event.pos()
        
        # If both left and right mouse buttons are pressed, set pan mode.
        if (event.buttons() & Qt.LeftButton) and (event.buttons() & Qt.RightButton):
            self.interaction_mode = 'pan'
            self.setCursor(QCursor(Qt.SizeAllCursor))
        else:
            # Check if user clicked in the nav-cube area.
            if self.isInNavCubeArea(event.x(), event.y()):
                self.pickNavCubeFace(event.x(), event.y())
                self.update()
                return

            # Otherwise, handle mouse button logic.
            if event.button() == Qt.MiddleButton:
                mods = event.modifiers()
                if mods & Qt.ShiftModifier:
                    self.interaction_mode = 'pan'
                    self.setCursor(QCursor(Qt.SizeAllCursor))
                elif mods & Qt.ControlModifier:
                    self.interaction_mode = 'zoom'
                    self.unsetCursor()
                else:
                    self.interaction_mode = 'orbit'
                    self.unsetCursor()
            else:
                self.interaction_mode = None
                self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton or (not (event.buttons() & Qt.LeftButton) or not (event.buttons() & Qt.RightButton)):
            self.interaction_mode = None
            self.unsetCursor()


    def mouseMoveEvent(self, event):
        if self.lastPos is None:
            return

        dx = event.x() - self.lastPos.x()
        dy = event.y() - self.lastPos.y()

        if self.interaction_mode == 'orbit':
            self.orbit_x += dx * 0.3
            self.orbit_y += dy * 0.3

        elif self.interaction_mode == 'pan':
            self.pan_x += dx * 0.10
            self.pan_y -= dy * 0.10

        elif self.interaction_mode == 'zoom':
            self.camera_distance *= (1.0 + dy * 0.01)
            # Optionally clamp
            # self.camera_distance = max(1.0, self.camera_distance)

        self.lastPos = event.pos()
        self.update()

    def wheelEvent(self, event):
        """
        Wheel event => adjust self.zoom for perspective or self.ortho_size for ortho.
        """
        angleDelta = event.angleDelta().y()  # positive => wheel up
        zoom_factor = 1.0 - angleDelta / 1000.0

        # For perspective mode
        self.zoom *= zoom_factor
        self.zoom = max(0.01, min(self.zoom, 100.0))

        # For orthographic mode
        self.ortho_size *= zoom_factor
        self.ortho_size = max(0.1, min(self.ortho_size, 10000.0))

        # Update projection so changes apply immediately
        self.makeCurrent()
        self.updateProjection()
        self.update()


class GcodeViewerWidget(QWidget):
    """
    A composite widget holding a QToolBar + the GcodeViewer3D below it.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self.viewer = GcodeViewer3D()

        self.toolbar = QToolBar("Viewer Tools")
        self.toolbar.setMovable(False)

        self.hideRapidsAction = QAction("Hide Rapids", self)
        self.hideRapidsAction.setCheckable(True)
        self.hideRapidsAction.setChecked(False)  # default: show rapids
        self.hideRapidsAction.toggled.connect(self.viewer.setHideRapids)
        self.toolbar.addAction(self.hideRapidsAction)

        self.orthoAction = QAction("Orthographic", self)
        self.orthoAction.setCheckable(True)
        self.orthoAction.setChecked(False)  # default: perspective
        self.orthoAction.toggled.connect(self.viewer.setOrthographic)
        self.toolbar.addAction(self.orthoAction)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.viewer)
        self.setLayout(layout)

    def loadSegments(self, segments):
        self.viewer.loadSegments(segments)


if __name__ == "__main__":
    # 1) Request MSAA globally (4 samples).
    fmt = QSurfaceFormat()
    fmt.setSamples(4)  # 4x MSAA
    QSurfaceFormat.setDefaultFormat(fmt)

    # 2) Create the application
    app = QApplication(sys.argv)

    # 3) Create the GcodeViewer3D
    viewer = GcodeViewer3D()
    viewer.setWindowTitle("G-code Viewer with 4x MSAA")

    # Build a more interesting set of segments:
    segs = [
        # --- Draw a square in G0 (rapid) moves at Z=0 ---
        Segment(
            type_="G0",
            coords={"X": 10, "Y": 0, "Z": 0, "E": 0, "F": 0},
            lineNb=1,
            line="G0 X10 Y0"
        ),
        Segment(
            type_="G0",
            coords={"X": 10, "Y": 10, "Z": 0, "E": 0, "F": 0},
            lineNb=2,
            line="G0 X10 Y10"
        ),
        Segment(
            type_="G0",
            coords={"X": 0, "Y": 10, "Z": 0, "E": 0, "F": 0},
            lineNb=3,
            line="G0 X0 Y10"
        ),
        Segment(
            type_="G0",
            coords={"X": 0, "Y": 0, "Z": 0, "E": 0, "F": 0},
            lineNb=4,
            line="G0 X0 Y0"
        ),

        # --- Move up to Z=5 and draw a square in G1 (feed) ---
        Segment(
            type_="G1",
            coords={"X": 0,  "Y": 0,  "Z": 5, "E": 0.0,  "F": 100},
            lineNb=5,
            line="G1 Z5 F100"
        ),
        Segment(
            type_="G1",
            coords={"X": 10, "Y": 0,  "Z": 5, "E": 0.0,  "F": 100},
            lineNb=6,
            line="G1 X10 Y0 Z5 F100"
        ),
        Segment(
            type_="G1",
            coords={"X": 10, "Y": 10, "Z": 5, "E": 2.5,  "F": 100},
            lineNb=7,
            line="G1 X10 Y10 Z5 E2.5 F100"
        ),
        Segment(
            type_="G1",
            coords={"X": 0,  "Y": 10, "Z": 5, "E": 5.0,  "F": 100},
            lineNb=8,
            line="G1 X0 Y10 Z5 E5.0 F100"
        ),
        Segment(
            type_="G1",
            coords={"X": 0,  "Y": 0,  "Z": 5, "E": 7.5,  "F": 100},
            lineNb=9,
            line="G1 X0 Y0 Z5 E7.5 F100"
        ),
    ]

    # Create the viewer
    viewer = GcodeViewer3D()
    viewer.setWindowTitle("G-code Viewer with 4x MSAA")

    # Show the widget so it creates a valid GL context
    viewer.resize(800, 600)
    viewer.show()

    # (Optional) Force Qt to process pending events
    app.processEvents()

    # Now it's safe to load your segments:
    viewer.loadSegments(segs)

    # Enter the main loop
    sys.exit(app.exec_())

