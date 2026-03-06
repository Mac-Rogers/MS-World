import math
import sys
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMainWindow,
    QWidget,
)


# -------------------------
# Minimal vector math
# -------------------------
class Vec3:
    __slots__ = ("x", "y", "z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __add__(self, other):
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, s: float):
        return Vec3(self.x * s, self.y * s, self.z * s)

    __rmul__ = __mul__

    def __truediv__(self, s: float):
        return Vec3(self.x / s, self.y / s, self.z / s)

    def dot(self, other) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other):
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self):
        l = self.length()
        if l < 1e-9:
            return Vec3(0, 0, 0)
        return self / l

    def tuple(self):
        return self.x, self.y, self.z


@dataclass
class Camera:
    yaw: float = 0.7
    pitch: float = 0.25
    distance: float = 12.0
    target: Vec3 = field(default_factory=lambda: Vec3(0, 0, 0))
    fov_deg: float = 45.0

    def position(self) -> Vec3:
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)
        offset = Vec3(self.distance * cp * sy, self.distance * sp, self.distance * cp * cy)
        return self.target + offset

    def basis(self):
        pos = self.position()
        forward = (self.target - pos).normalized()
        world_up = Vec3(0, 1, 0)
        right = forward.cross(world_up).normalized()
        if right.length() < 1e-8:
            right = Vec3(1, 0, 0)
        up = right.cross(forward).normalized()
        return pos, forward, right, up


@dataclass
class TextBand:
    text: str = "Double-click to edit"
    latitude_deg: float = 0.0  # 0 = equator
    size_px: int = 18
    color: QColor = field(default_factory=lambda: QColor(30, 30, 30))


@dataclass
class SphereObject:
    center: Vec3
    radius: float = 1.5
    bands: List[TextBand] = field(default_factory=lambda: [TextBand()])
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class Viewport3D(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.camera = Camera()
        self.spheres: List[SphereObject] = [SphereObject(center=Vec3(0, 0, 0), radius=1.8)]
        self.selected_id: Optional[str] = self.spheres[0].id

        self.last_mouse: Optional[QPoint] = None
        self.orbiting = False
        self.panning = False

        self.background_top = QColor(12, 16, 24)
        self.background_bottom = QColor(30, 40, 55)
        self.light_dir = Vec3(-0.5, 0.8, 0.7).normalized()

        self.move_speed = 0.35
        self.status_text = "Left drag: orbit | Right drag: pan | Wheel: zoom | Double-click sphere: edit | Ctrl+N: new sphere"

    # ---------- camera + projection ----------
    def project(self, p_world: Vec3):
        pos, forward, right, up = self.camera.basis()
        rel = p_world - pos
        x_cam = rel.dot(right)
        y_cam = rel.dot(up)
        z_cam = rel.dot(forward)
        if z_cam <= 0.01:
            return None

        h = max(1, self.height())
        w = max(1, self.width())
        f = 0.5 * h / math.tan(math.radians(self.camera.fov_deg) * 0.5)
        sx = w * 0.5 + (x_cam * f / z_cam)
        sy = h * 0.5 - (y_cam * f / z_cam)
        return QPointF(sx, sy), z_cam

    def projected_radius(self, center: Vec3, radius: float) -> Optional[float]:
        proj = self.project(center)
        if proj is None:
            return None
        pos, _, right, _ = self.camera.basis()
        edge = center + right * radius
        p0 = self.project(center)
        p1 = self.project(edge)
        if p0 is None or p1 is None:
            return None
        return math.hypot(p1[0].x() - p0[0].x(), p1[0].y() - p0[0].y())

    # ---------- sphere management ----------
    def selected_sphere(self) -> Optional[SphereObject]:
        for s in self.spheres:
            if s.id == self.selected_id:
                return s
        return None

    def add_sphere_in_front(self):
        pos, forward, _, _ = self.camera.basis()
        center = self.camera.target + forward * 1.0
        radius = 1.5
        sphere = SphereObject(center=center, radius=radius)
        self.spheres.append(sphere)
        self.selected_id = sphere.id
        self.update()

    def pick_sphere(self, point: QPointF) -> Optional[str]:
        best = None
        best_depth = float("inf")
        for sphere in self.spheres:
            proj = self.project(sphere.center)
            pr = self.projected_radius(sphere.center, sphere.radius)
            if proj is None or pr is None:
                continue
            screen_pt, depth = proj
            d = math.hypot(point.x() - screen_pt.x(), point.y() - screen_pt.y())
            if d <= pr and depth < best_depth:
                best_depth = depth
                best = sphere.id
        return best

    # ---------- painting ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        bg = QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0.0, self.background_top)
        bg.setColorAt(1.0, self.background_bottom)
        painter.fillRect(self.rect(), bg)

        items = []
        for s in self.spheres:
            proj = self.project(s.center)
            pr = self.projected_radius(s.center, s.radius)
            if proj is None or pr is None or pr < 2:
                continue
            screen_pt, depth = proj
            items.append((depth, s, screen_pt, pr))
        items.sort(reverse=True, key=lambda t: t[0])

        for _, sphere, center2d, rad_px in items:
            self.draw_sphere(painter, sphere, center2d, rad_px)
            for band in sphere.bands:
                self.draw_text_band(painter, sphere, band)

        painter.setPen(QColor(230, 235, 240, 220))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(14, self.height() - 16, self.status_text)

        sel = self.selected_sphere()
        if sel:
            painter.setPen(QColor(245, 248, 250, 200))
            painter.drawText(14, 26, f"Selected sphere | text: {sel.bands[0].text[:60]}")

    def draw_sphere(self, painter: QPainter, sphere: SphereObject, center2d: QPointF, rad_px: float):
        rect = QRectF(center2d.x() - rad_px, center2d.y() - rad_px, 2 * rad_px, 2 * rad_px)

        # Soft shadow
        shadow_rect = rect.adjusted(rad_px * 0.08, rad_px * 0.1, rad_px * 0.28, rad_px * 0.3)
        shadow = QRadialGradient(shadow_rect.center(), shadow_rect.width() * 0.58)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 55))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow)
        painter.drawEllipse(shadow_rect)

        # Sphere fill with highlight offset toward light direction
        light_offset = QPointF(-rad_px * 0.28, -rad_px * 0.33)
        grad = QRadialGradient(center2d + light_offset, rad_px * 0.2, center2d + light_offset)
        grad.setColorAt(0.0, QColor(255, 255, 255))
        grad.setColorAt(0.35, QColor(246, 247, 249))
        grad.setColorAt(0.75, QColor(228, 231, 236))
        grad.setColorAt(1.0, QColor(192, 198, 207))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.2))
        painter.drawEllipse(rect)

        # Rim / ambient curve
        rim = QRadialGradient(center2d, rad_px)
        rim.setColorAt(0.82, QColor(0, 0, 0, 0))
        rim.setColorAt(1.0, QColor(40, 48, 58, 45))
        painter.setBrush(rim)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)

        # Selection highlight
        if sphere.id == self.selected_id:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(100, 180, 255, 215), 2.2))
            painter.drawEllipse(rect.adjusted(-4, -4, 4, 4))

    def draw_text_band(self, painter: QPainter, sphere: SphereObject, band: TextBand):
        text = band.text
        if not text:
            return

        lat = math.radians(max(-80.0, min(80.0, band.latitude_deg)))
        # Use front-facing arc only. Text wraps around horizontally by using longitude.
        longitudes = self.compute_band_layout(sphere, band, text)
        if not longitudes:
            return

        font = QFont("Segoe UI", band.size_px)
        painter.setFont(font)
        painter.setPen(band.color)

        for ch, lon in zip(text, longitudes):
            # front hemisphere visibility by surface normal facing camera
            p, east, normal = self.surface_frame(sphere, lon, lat)
            if p is None:
                continue
            cam_pos, _, _, _ = self.camera.basis()
            view_dir = (cam_pos - p).normalized()
            facing = normal.dot(view_dir)
            if facing <= 0.05:
                continue

            proj = self.project(p)
            if proj is None:
                continue
            screen_pt, _ = proj

            # Character tangent direction in screen space
            p_east = p + east * (sphere.radius * 0.08)
            proj_east = self.project(p_east)
            if proj_east is None:
                continue
            east_pt, _ = proj_east
            dx = east_pt.x() - screen_pt.x()
            dy = east_pt.y() - screen_pt.y()
            angle_deg = math.degrees(math.atan2(dy, dx))

            alpha = int(max(30, min(255, 70 + 185 * facing)))
            painter.save()
            painter.translate(screen_pt)
            painter.rotate(angle_deg)
            painter.setPen(QColor(band.color.red(), band.color.green(), band.color.blue(), alpha))
            # Draw a tiny shadow for readability
            painter.drawText(QPointF(1.0, 1.0), ch)
            painter.setPen(QColor(band.color.red(), band.color.green(), band.color.blue(), alpha))
            painter.drawText(QPointF(0.0, 0.0), ch)
            painter.restore()

    def compute_band_layout(self, sphere: SphereObject, band: TextBand, text: str):
        # Approximate width allocation by glyph count. This is an MVP and intentionally simple.
        circumference_px = self.estimated_visible_circumference_px(sphere, band.latitude_deg)
        if circumference_px <= 10:
            return []

        avg_char_px = band.size_px * 0.62
        total_px = len(text) * avg_char_px
        arc_fraction = min(0.92, max(0.08, total_px / max(circumference_px, 1)))
        total_angle = 2 * math.pi * arc_fraction
        start = -0.5 * total_angle

        positions = []
        if len(text) == 1:
            return [0.0]
        for i in range(len(text)):
            t = i / (len(text) - 1)
            positions.append(start + t * total_angle)
        return positions

    def estimated_visible_circumference_px(self, sphere: SphereObject, latitude_deg: float) -> float:
        lat = math.radians(latitude_deg)
        ring_radius_world = sphere.radius * math.cos(lat)
        center = sphere.center + Vec3(0, sphere.radius * math.sin(lat), 0)
        pr = self.projected_radius(center, ring_radius_world)
        if pr is None:
            return 0.0
        return 2 * math.pi * pr

    def surface_frame(self, sphere: SphereObject, lon: float, lat: float):
        # longitude around Y axis, latitude around equator
        cp = math.cos(lat)
        sp = math.sin(lat)
        cl = math.cos(lon)
        sl = math.sin(lon)

        normal = Vec3(cp * sl, sp, cp * cl).normalized()
        point = sphere.center + normal * sphere.radius
        east = Vec3(cp * cl, 0.0, -cp * sl).normalized()
        return point, east, normal

    # ---------- input ----------
    def mousePressEvent(self, event):
        self.last_mouse = event.position().toPoint()
        if event.button() == Qt.LeftButton:
            picked = self.pick_sphere(event.position())
            if picked:
                self.selected_id = picked
            self.orbiting = True
        elif event.button() == Qt.RightButton:
            self.panning = True
        self.update()

    def mouseMoveEvent(self, event):
        if self.last_mouse is None:
            self.last_mouse = event.position().toPoint()
            return

        current = event.position().toPoint()
        delta = current - self.last_mouse
        self.last_mouse = current

        if self.orbiting:
            self.camera.yaw -= delta.x() * 0.008
            self.camera.pitch += delta.y() * 0.008
            self.camera.pitch = max(-1.45, min(1.45, self.camera.pitch))
            self.update()
        elif self.panning:
            _, _, right, up = self.camera.basis()
            scale = 0.005 * self.camera.distance
            self.camera.target = self.camera.target - right * (delta.x() * scale) + up * (delta.y() * scale)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.orbiting = False
        elif event.button() == Qt.RightButton:
            self.panning = False
        self.last_mouse = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 120.0
        self.camera.distance *= math.pow(0.88, delta)
        self.camera.distance = max(2.0, min(60.0, self.camera.distance))
        self.update()

    def mouseDoubleClickEvent(self, event):
        picked = self.pick_sphere(event.position())
        if not picked:
            return
        self.selected_id = picked
        sphere = self.selected_sphere()
        if sphere is None:
            return
        current = sphere.bands[0].text
        text, ok = QInputDialog.getMultiLineText(self, "Edit sphere text", "Text around sphere:", current)
        if ok:
            sphere.bands[0].text = text.strip() or current
            self.update()

    def keyPressEvent(self, event):
        pos, forward, right, up = self.camera.basis()
        speed = self.move_speed * max(1.0, self.camera.distance / 10.0)

        if event.key() == Qt.Key_W:
            self.camera.target = self.camera.target + forward * speed
        elif event.key() == Qt.Key_S:
            self.camera.target = self.camera.target - forward * speed
        elif event.key() == Qt.Key_A:
            self.camera.target = self.camera.target - right * speed
        elif event.key() == Qt.Key_D:
            self.camera.target = self.camera.target + right * speed
        elif event.key() == Qt.Key_Q:
            self.camera.target = self.camera.target + up * speed
        elif event.key() == Qt.Key_E:
            self.camera.target = self.camera.target - up * speed
        elif event.key() == Qt.Key_F and self.selected_sphere() is not None:
            self.camera.target = self.selected_sphere().center
        elif event.key() == Qt.Key_Delete and self.selected_sphere() is not None and len(self.spheres) > 1:
            sid = self.selected_id
            self.spheres = [s for s in self.spheres if s.id != sid]
            self.selected_id = self.spheres[0].id if self.spheres else None
        else:
            super().keyPressEvent(event)
            return
        self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sphere Writer MVP")
        self.resize(1400, 900)

        self.viewport = Viewport3D()
        self.setCentralWidget(self.viewport)

        new_action = QAction("New Sphere", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self.viewport.add_sphere_in_front)
        self.addAction(new_action)

        edit_action = QAction("Edit Text", self)
        edit_action.setShortcut(QKeySequence("Ctrl+E"))
        edit_action.triggered.connect(self.edit_selected)
        self.addAction(edit_action)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.viewport.add_sphere_in_front)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.edit_selected)

        self.statusBar().showMessage(
            "Ctrl+N: new sphere | Ctrl+E or double-click: edit | WASDQE: move | F: focus selected | Delete: delete selected"
        )

    def edit_selected(self):
        sphere = self.viewport.selected_sphere()
        if sphere is None:
            return
        current = sphere.bands[0].text
        text, ok = QInputDialog.getMultiLineText(self, "Edit sphere text", "Text around sphere:", current)
        if ok:
            sphere.bands[0].text = text.strip() or current
            self.viewport.update()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Sphere Writer MVP")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
