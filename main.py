import sys
import math
import textwrap
import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import ctypes

# ── tkinter file dialog (stdlib, no extra install needed) ─────────────────────
import tkinter as tk
from tkinter import filedialog

def open_image_dialog():
    """Open a native file-picker and return the chosen path, or None."""
    root = tk.Tk()
    root.withdraw()          # hide the empty Tk window
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(
        title="Choose an image for the sphere",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tga *.webp"),
            ("All files",   "*.*"),
        ]
    )
    root.destroy()
    return path if path else None

# ── Constants ────────────────────────────────────────────────────────────────
# We'll set WIN_W, WIN_H at runtime from the display resolution
WIN_W, WIN_H = 0, 0
FPS          = 60
BASE_RADIUS  = 1.5
RADIUS_PER_CHAR = 0.012
MAX_RADIUS   = 4.5
FONT_SIZES = [48, 64, 80, 100, 120, 150, 200]
FONT_SIZE_LABELS = ["48", "64", "80", "100", "120", "150", "200"]
BANNER_H     = 300
FONT_SIZE    = 80   # default font size

COLORS = [
    ((0.20, 0.20, 0.20), (1.0,  1.0,  1.0 )),
    ((0.30, 0.30, 0.30), (0.95, 0.95, 0.95)),
    ((0.25, 0.25, 0.25), (0.98, 0.98, 0.98)),
    ((0.15, 0.15, 0.15), (0.93, 0.93, 0.93)),
    ((0.35, 0.35, 0.35), (0.97, 0.97, 0.97)),
]

# ── Links between spheres ────────────────────────────────────────────────────
# Each link is a frozenset of two sphere IDs
links = set()

# ── Banner ────────────────────────────────────────────────────────────────────
class Banner:
    def __init__(self, path="banner.png"):
        self.tex = None; self.w = self.h = 0
        try:
            img = pygame.image.load(path).convert_alpha()
            iw, ih = img.get_width(), img.get_height()
            if ih > BANNER_H:
                scale = BANNER_H / ih
                img = pygame.transform.smoothscale(img, (int(iw * scale), BANNER_H))
            self.w, self.h = img.get_size()
            data = pygame.image.tostring(img, "RGBA", True)
            tid  = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tid)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.w, self.h,
                         0, GL_RGBA, GL_UNSIGNED_BYTE, data)
            self.tex = tid
        except Exception as e:
            print(f"[banner] {e}")

    def draw(self):
        if not self.tex: return
        _draw_quad(self.tex, 0, 0, WIN_W, self.h)

    def free(self):
        if self.tex: glDeleteTextures([self.tex])


# ── Sidebar ───────────────────────────────────────────────────────────────────
class Sidebar:
    def __init__(self, path="sidebar.png"):
        self.tex = None; self.w = self.h = 0
        try:
            img    = pygame.image.load(path).convert_alpha()
            iw, ih = img.get_width(), img.get_height()
            avail_h = WIN_H - BANNER_H
            if ih > avail_h:
                scale = avail_h / ih
                img = pygame.transform.smoothscale(img, (int(iw * scale), avail_h))
            self.w, self.h = img.get_size()
            data = pygame.image.tostring(img, "RGBA", True)
            tid  = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tid)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.w, self.h,
                         0, GL_RGBA, GL_UNSIGNED_BYTE, data)
            self.tex = tid
        except Exception as e:
            print(f"[sidebar] {e}")

    def draw(self):
        if not self.tex: return
        _draw_quad(self.tex, 0, BANNER_H, self.w, BANNER_H + self.h)

    def free(self):
        if self.tex: glDeleteTextures([self.tex])


# ── Dropdown Menu ─────────────────────────────────────────────────────────────
class DropdownMenu:
    """A simple font-size dropdown rendered in the 2-D ortho pass."""

    def __init__(self, x, y, w, item_h=28):
        self.x      = x
        self.y      = y
        self.w      = w
        self.item_h = item_h
        self.open   = False
        self.selected_idx = 2          # index into FONT_SIZES (default 80)
        self.font   = pygame.font.SysFont("calibri", 20, bold=False)

    @property
    def current_size(self):
        return FONT_SIZES[self.selected_idx]

    @property
    def button_rect(self):
        """Rect of the closed button (screen coords, y-down)."""
        return (self.x, self.y, self.w, self.item_h)

    def _item_rects(self):
        """Yield (index, x, y, w, h) for each dropdown row."""
        bx, by, bw, bh = self.button_rect
        for i in range(len(FONT_SIZES)):
            iy = by + bh + i * self.item_h
            yield i, bx, iy, bw, self.item_h

    def hit_test(self, mx, my):
        """Return True if the click was consumed by this menu."""
        bx, by, bw, bh = self.button_rect

        # Click on the button itself → toggle
        if bx <= mx <= bx + bw and by <= my <= by + bh:
            self.open = not self.open
            return True

        # Click on an open item → select
        if self.open:
            for i, ix, iy, iw, ih in self._item_rects():
                if ix <= mx <= ix + iw and iy <= my <= iy + ih:
                    self.selected_idx = i
                    self.open = False
                    return True

            # Click elsewhere → close
            self.open = False
            return True

        return False

    def draw_gl(self):
        """Draw the dropdown using immediate-mode GL quads + text textures."""
        bx, by, bw, bh = self.button_rect

        # ── button background ─────────────────────────────────────────────
        self._draw_rect(bx, by, bw, bh, (1.0, 1.0, 1.0, 1.0))

        # ── button label ──────────────────────────────────────────────────
        label = f"{self.current_size}"
        self._draw_text(label, bx + 8, by + 4, (0.15, 0.15, 0.15))

        if not self.open:
            return

        # ── dropdown items ────────────────────────────────────────────────
        for i, ix, iy, iw, ih in self._item_rects():
            if i == self.selected_idx:
                self._draw_rect(ix, iy, iw, ih, (0.22, 0.47, 0.85, 0.95))
            else:
                self._draw_rect(ix, iy, iw, ih, (1.0, 1.0, 1.0, 0.97))

            tc = (1.0, 1.0, 1.0) if i == self.selected_idx else (0.15, 0.15, 0.15)
            self._draw_text(FONT_SIZE_LABELS[i], ix + 8, iy + 4, tc)

    # ── GL helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _draw_rect(x, y, w, h, color):
        glDisable(GL_TEXTURE_2D)
        glColor4f(*color)
        glBegin(GL_QUADS)
        glVertex2f(x,     y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x,     y + h)
        glEnd()

    def _draw_text(self, text, x, y, color):
        """Render a small text string via a throwaway GL texture."""
        surf = self.font.render(text, True,
                                tuple(int(c * 255) for c in color))
        surf = surf.convert_alpha()
        tw, th = surf.get_size()
        data = pygame.image.tostring(surf, "RGBA", True)
        tid  = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tid)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tw, th,
                     0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glEnable(GL_TEXTURE_2D)
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(x,      y)
        glTexCoord2f(1, 1); glVertex2f(x + tw, y)
        glTexCoord2f(1, 0); glVertex2f(x + tw, y + th)
        glTexCoord2f(0, 0); glVertex2f(x,      y + th)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        glDeleteTextures([tid])


# ── Shared texture helpers ────────────────────────────────────────────────────
def _upload_surface(surf, wrap_s=GL_CLAMP_TO_EDGE, wrap_t=GL_CLAMP_TO_EDGE, mipmap=False):
    """Upload a pygame Surface as a GL texture; return the texture ID."""
    data = pygame.image.tostring(surf, "RGBA", True)
    tid  = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tid)
    min_f = GL_LINEAR_MIPMAP_LINEAR if mipmap else GL_LINEAR
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, min_f)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap_s)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap_t)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, surf.get_width(), surf.get_height(),
                 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    if mipmap:
        glGenerateMipmap(GL_TEXTURE_2D)
    return tid


def _draw_quad(tid, x0, y0, x1, y1):
    """Draw a textured quad in the current 2-D ortho pass."""
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tid)
    glColor4f(1, 1, 1, 1)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 1); glVertex2f(x0, y0)
    glTexCoord2f(1, 1); glVertex2f(x1, y0)
    glTexCoord2f(1, 0); glVertex2f(x1, y1)
    glTexCoord2f(0, 0); glVertex2f(x0, y1)
    glEnd()
    glDisable(GL_TEXTURE_2D)


# ── Sphere ───────────────────────────────────────────────────────────────────
class Sphere:
    _id_counter = 0

    def __init__(self, position, color_idx=0, font_size=None):
        Sphere._id_counter += 1
        self.id         = Sphere._id_counter
        self.pos        = list(position)
        self.text       = ""
        self.image_path = None
        self.color_idx  = color_idx % len(COLORS)
        self.font_size  = font_size if font_size else FONT_SIZE
        self.texture_id = None
        self.quadric    = gluNewQuadric()
        gluQuadricTexture(self.quadric, GL_TRUE)
        gluQuadricNormals(self.quadric, GLU_SMOOTH)
        self._rebuild_texture()
        self.spin  = 0.0
        self.angle = 0.0

    # ── mode helpers ─────────────────────────────────────────────────────────
    @property
    def is_image(self):
        return self.image_path is not None

    def load_image(self, path):
        """Replace sphere content with an image texture."""
        try:
            img = pygame.image.load(path).convert_alpha()
            # Keep the image's natural aspect ratio on the sphere.
            # We upload it at a fixed size; gluSphere will wrap it around.
            img = pygame.transform.smoothscale(img, (2048, 1024))
            if self.texture_id is not None:
                glDeleteTextures([self.texture_id])
            self.texture_id = _upload_surface(
                img,
                wrap_s=GL_REPEAT,
                wrap_t=GL_CLAMP_TO_EDGE,
                mipmap=True,
            )
            self.image_path = path
            self.text       = ""   # clear any text
        except Exception as e:
            print(f"[sphere] could not load image {path}: {e}")

    # ── radius ───────────────────────────────────────────────────────────────
    @property
    def radius(self):
        if self.is_image:
            return BASE_RADIUS
        width = 2048
        chars_per_line = max(12, int(width / (self.font_size * 0.60)))
        display  = self.text if self.text else ""
        wrapped  = []
        for raw in display.splitlines() or [display]:
            wrapped.extend(textwrap.wrap(raw, width=chars_per_line) or [""])
        line_count = max(1, len(wrapped))
        start_grow = 2
        if line_count > start_grow:
            r = BASE_RADIUS + (line_count - start_grow) * (RADIUS_PER_CHAR * 24)
        else:
            r = BASE_RADIUS
        return min(r, MAX_RADIUS)

    # ── text editing ─────────────────────────────────────────────────────────
    def add_char(self, ch):
        if self.is_image: return
        self.text += ch
        self._rebuild_texture()

    def backspace(self):
        if self.is_image: return
        if self.text:
            self.text = self.text[:-1]
            self._rebuild_texture()

    # ── texture build (text mode) ─────────────────────────────────────────────
    def _rebuild_texture(self):
        if self.is_image:
            return
        text_color, bg_color = COLORS[self.color_idx]
        width = 2048

        r = self.radius
        height = int(512 * (r / BASE_RADIUS))
        height = max(512, min(height, 4096))

        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        bg   = tuple(int(c * 255) for c in bg_color)
        surf.fill((*bg, 255))

        font           = pygame.font.SysFont("monospace", self.font_size, bold=True)
        chars_per_line = max(12, int(width / (self.font_size * 0.60)))
        display        = self.text if self.text else ""
        lines          = []
        for raw in display.splitlines() or [display]:
            lines.extend(textwrap.wrap(raw, width=chars_per_line) or [""])

        tc     = tuple(int(c * 255) for c in text_color)
        line_h = self.font_size + 8
        total_h = len(lines) * line_h
        y = (height - total_h) // 2

        for line in lines:
            rendered = font.render(line, True, tc)
            surf.blit(rendered, (20, y))
            y += line_h

        if self.texture_id is not None:
            glDeleteTextures([self.texture_id])
        self.texture_id = _upload_surface(
            surf, wrap_s=GL_REPEAT, wrap_t=GL_CLAMP_TO_EDGE
        )

    # ── draw ─────────────────────────────────────────────────────────────────
    def draw(self, selected):
        glPushMatrix()
        glTranslatef(*self.pos)
        glRotatef(-90, 1, 0, 0)
        glRotatef(180, 0, 0, 1)   # face the camera on initial load
        glRotatef(self.angle, 0, 1, 0)
        r = self.radius

        if selected:
            glDisable(GL_TEXTURE_2D); glDisable(GL_LIGHTING)
            glColor4f(0.91, 0.30, 0.16, 0.6)
            glLineWidth(2.5)
            self._draw_circle(r + 0.08, 80)
            glRotatef(90, 1, 0, 0)
            self._draw_circle(r + 0.08, 80)
            glRotatef(-90, 1, 0, 0)
            glLineWidth(1.0)
            glEnable(GL_LIGHTING)
            glEnable(GL_TEXTURE_2D)

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glColor4f(1, 1, 1, 1)
        gluSphere(self.quadric, r, 64, 64)
        glDisable(GL_TEXTURE_2D)
        glPopMatrix()

    def _draw_circle(self, r, segs):
        glBegin(GL_LINE_LOOP)
        for i in range(segs):
            a = 2 * math.pi * i / segs
            glVertex3f(math.cos(a) * r, math.sin(a) * r, 0)
        glEnd()

    def cleanup(self):
        if self.texture_id: glDeleteTextures([self.texture_id])
        gluDeleteQuadric(self.quadric)


# ── Camera ────────────────────────────────────────────────────────────────────
class Camera:
    def __init__(self):
        self.theta  = 0.3
        self.phi    = 1.2
        self.radius = 18.0
        self.target = [0.0, 0.0, 0.0]

    def apply(self):
        glMatrixMode(GL_MODELVIEW); glLoadIdentity()
        eye = self._eye()
        gluLookAt(eye[0], eye[1], eye[2],
                  self.target[0], self.target[1], self.target[2], 0, 1, 0)

    def _eye(self):
        return (
            self.target[0] + self.radius * math.sin(self.phi) * math.sin(self.theta),
            self.target[1] + self.radius * math.cos(self.phi),
            self.target[2] + self.radius * math.sin(self.phi) * math.cos(self.theta),
        )

    def orbit(self, dx, dy):
        self.theta -= dx * 0.007
        self.phi    = max(0.15, min(math.pi - 0.15, self.phi + dy * 0.007))

    def pan(self, dx, dy):
        rx = math.cos(self.theta);  rz = -math.sin(self.theta)
        ux = math.cos(self.phi) * math.sin(self.theta)
        uy = -math.sin(self.phi)
        uz = math.cos(self.phi) * math.cos(self.theta)
        s  = self.radius * 0.001
        self.target[0] += (-dx * rx + dy * ux) * s
        self.target[1] +=  dy * uy * s
        self.target[2] += (-dx * rz + dy * uz) * s

    def zoom(self, delta):
        self.radius = max(3, min(80, self.radius - delta * 0.8))

    def look_at(self, pos, radius):
        self.target = list(pos); self.radius = radius * 4.5


# ── Picking ───────────────────────────────────────────────────────────────────
def pick_sphere(spheres, mx, my, camera):
    proj = glGetDoublev(GL_PROJECTION_MATRIX)
    mv   = glGetDoublev(GL_MODELVIEW_MATRIX)
    vp   = glGetIntegerv(GL_VIEWPORT)
    near = gluUnProject(mx, WIN_H - my, 0.0, mv, proj, vp)
    far  = gluUnProject(mx, WIN_H - my, 1.0, mv, proj, vp)
    ro   = np.array(near)
    rd   = np.array(far) - ro;  rd /= np.linalg.norm(rd)
    best, best_t = None, 1e18
    for s in spheres:
        oc   = ro - np.array(s.pos)
        b    = np.dot(oc, rd)
        c    = np.dot(oc, oc) - s.radius ** 2
        disc = b * b - c
        if disc >= 0:
            t = -b - math.sqrt(disc)
            if 0 < t < best_t:
                best_t = t; best = s
    return best


def project_depth(world_pos):
    proj = glGetDoublev(GL_PROJECTION_MATRIX)
    mv   = glGetDoublev(GL_MODELVIEW_MATRIX)
    vp   = glGetIntegerv(GL_VIEWPORT)
    _, _, wz = gluProject(world_pos[0], world_pos[1], world_pos[2], mv, proj, vp)
    return wz


def unproject_at_depth(mx, my, depth):
    proj = glGetDoublev(GL_PROJECTION_MATRIX)
    mv   = glGetDoublev(GL_MODELVIEW_MATRIX)
    vp   = glGetIntegerv(GL_VIEWPORT)
    return gluUnProject(mx, WIN_H - my, depth, mv, proj, vp)


# ── HUD ───────────────────────────────────────────────────────────────────────
class HUD:
    def __init__(self):
        self.font_big = pygame.font.SysFont("monospace", 14, bold=True)
        self.font_sm  = pygame.font.SysFont("monospace", 12)

    def draw(self, screen, spheres, selected, cursor_visible):
        surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)

        y = BANNER_H + 6
        surf.blit(self.font_sm.render(
            "drag=orbit  right-drag=pan  scroll=zoom  click=select  Ctrl+N=new  Ctrl+I=image  Del=delete",
            True, (80, 78, 72)), (16, y)); y += 18
        surf.blit(self.font_sm.render("SPHERES", True, (100, 96, 90)), (16, y)); y += 18

        for s in spheres:
            col     = (232, 77, 42) if s is selected else (180, 175, 165)
            if s.is_image:
                import os
                preview = f"[img] {os.path.basename(s.image_path)[:18]}"
            else:
                preview = s.text[:20] + ("…" if len(s.text) > 20 else "") if s.text else ""
            surf.blit(self.font_sm.render(f"● #{s.id}  {preview}", True, col), (16, y)); y += 18

        if selected:
            if selected.is_image:
                import os
                info = f"Selected: #{selected.id}  |  image: {os.path.basename(selected.image_path)}"
                hint = "Ctrl+I to replace image"
            else:
                info = f"Selected: #{selected.id}  |  {len(selected.text)} chars  |  R={selected.radius:.2f}"
                hint = "Ctrl+I (on empty sphere) to add image"
            surf.blit(self.font_sm.render(info, True, (232, 77, 42)), (16, WIN_H - 50))

            if not selected.is_image:
                display = selected.text + ("|" if cursor_visible else " ")
                lines   = textwrap.wrap(display, 80) or [display]
                for i, line in enumerate(lines[-3:]):
                    surf.blit(self.font_sm.render(line, True, (200, 200, 200)),
                              (16, WIN_H - 30 + i * 14 - (len(lines[-3:]) - 1) * 14))
            else:
                surf.blit(self.font_sm.render(hint, True, (160, 160, 140)), (16, WIN_H - 30))
        else:
            surf.blit(self.font_sm.render("Click a sphere to select it, then type  |  Ctrl+I on empty sphere = image",
                                           True, (90, 86, 80)), (16, WIN_H - 30))

        screen.blit(surf, (0, 0))


# ── GL setup ──────────────────────────────────────────────────────────────────
def setup_gl():
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LIGHTING); glEnable(GL_LIGHT0); glEnable(GL_LIGHT1)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glLightfv(GL_LIGHT0, GL_POSITION, [ 8.0,  12.0,  10.0, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [ 1.0,   0.85,  0.7, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [ 0.5,   0.5,   0.5, 1.0])
    glLightfv(GL_LIGHT1, GL_POSITION, [-6.0,  -4.0,  -8.0, 1.0])
    glLightfv(GL_LIGHT1, GL_DIFFUSE,  [ 0.2,   0.3,   0.5, 1.0])
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.15, 0.15, 0.18, 1.0])
    glViewport(0, 0, WIN_W, WIN_H)
    glMatrixMode(GL_PROJECTION); glLoadIdentity()
    gluPerspective(55, WIN_W / WIN_H, 0.1, 200)
    glMatrixMode(GL_MODELVIEW)


def draw_grid():
    glDisable(GL_LIGHTING); glDisable(GL_TEXTURE_2D)
    glColor4f(0.15, 0.15, 0.2, 0.6); glLineWidth(1.0)
    glBegin(GL_LINES)
    for i in range(-30, 31, 2):
        glVertex3f(i, -6, -30); glVertex3f(i,  -6,  30)
        glVertex3f(-30, -6, i); glVertex3f(30, -6,   i)
    glEnd()
    glEnable(GL_LIGHTING)


def draw_links(spheres):
    """Draw connecting lines between linked spheres."""
    global links
    if not links:
        return
    by_id = {s.id: s for s in spheres}
    glDisable(GL_LIGHTING); glDisable(GL_TEXTURE_2D)
    glColor4f(0.35, 0.35, 0.40, 0.9)
    glLineWidth(2.5)
    glBegin(GL_LINES)
    for link in links:
        ids = list(link)
        if len(ids) == 2 and ids[0] in by_id and ids[1] in by_id:
            a = by_id[ids[0]]
            b = by_id[ids[1]]
            glVertex3f(*a.pos)
            glVertex3f(*b.pos)
    glEnd()
    glLineWidth(1.0)
    glEnable(GL_LIGHTING)


def new_sphere_position(spheres):
    """Return a position for a new sphere that doesn't overlap existing ones."""
    if not spheres:
        return [0.0, 0.0, 0.0]
    # Place new sphere to the right of the rightmost existing sphere
    max_x = max(s.pos[0] + s.radius for s in spheres)
    return [max_x + BASE_RADIUS * 2.5, 0.0, 0.0]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global WIN_W, WIN_H, links

    # Tell Windows we are DPI-aware so we get real pixel coordinates
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    pygame.init()

    # Get screen size and use a borderless window instead of FULLSCREEN
    info = pygame.display.Info()
    WIN_W = info.current_w
    WIN_H = info.current_h
    pygame.display.set_mode((WIN_W, WIN_H), DOUBLEBUF | OPENGL | NOFRAME)
    pygame.display.set_caption("MS World")
    pygame.key.set_repeat(400, 50)

    setup_gl()

    banner   = Banner("banner.png")
    sidebar  = Sidebar("sidebar.png")
    dropdown = DropdownMenu(x=350, y=BANNER_H - 160, w=45)
    camera   = Camera()
    hud      = HUD()
    spheres  = []; selected = None; color_idx = 0
    selected_set = set()   # for multi-select (shift+click)

    s = Sphere((0, 0, 0), color_idx, font_size=dropdown.current_size)
    s.text = "Hello world"; s._rebuild_texture(); spheres.append(s)

    mouse_down_left  = False
    mouse_down_right = False
    last_mouse       = (0, 0)
    dragged          = False
    dragging_sphere  = None
    drag_depth       = None

    clock = pygame.time.Clock(); cursor_timer = 0; cursor_visible = True

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        cursor_timer += dt
        if cursor_timer > 0.5:
            cursor_timer = 0; cursor_visible = not cursor_visible

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False

            elif event.type == KEYDOWN:
                ctrl  = pygame.key.get_mods() & KMOD_CTRL
                shift = pygame.key.get_mods() & KMOD_SHIFT

                # ── L : link all spheres in selected_set ──────────────────────
                if event.key == K_l and not ctrl:
                    sel_list = list(selected_set)
                    if len(sel_list) >= 2:
                        # Link every pair
                        for i in range(len(sel_list)):
                            for j in range(i + 1, len(sel_list)):
                                pair = frozenset((sel_list[i].id, sel_list[j].id))
                                if pair in links:
                                    links.discard(pair)  # toggle off
                                else:
                                    links.add(pair)      # toggle on

                # ── Ctrl+I : load image onto selected (empty or image) sphere ─
                elif ctrl and event.key == K_i:
                    if selected is not None and (not selected.text or selected.is_image):
                        path = open_image_dialog()
                        if path:
                            selected.load_image(path)
                        pygame.event.clear()

                # ── Ctrl+N : new sphere ───────────────────────────────────────
                elif ctrl and event.key == K_n:
                    pos = new_sphere_position(spheres)
                    sp  = Sphere(pos, color_idx % len(COLORS), font_size=dropdown.current_size)
                    color_idx += 1; spheres.append(sp); selected = sp
                    selected_set = {sp}
                    camera.look_at(pos, sp.radius)

                # ── Text editing (non-image sphere) ───────────────────────────
                elif selected and not selected.is_image:
                    if   event.key == K_BACKSPACE: selected.backspace()
                    elif event.key == K_RETURN:    selected.add_char('\n')
                    elif event.key == K_ESCAPE:
                        selected = None; selected_set.clear()
                    elif not ctrl and event.unicode and event.unicode.isprintable():
                        if event.key != K_l:  # don't type 'l' when linking
                            selected.add_char(event.unicode)

                elif selected and event.key == K_ESCAPE:
                    selected = None; selected_set.clear()

                # ── Delete empty sphere ───────────────────────────────────────
                if not ctrl and event.key == K_DELETE:
                    if selected and not selected.text and not selected.is_image:
                        # Remove any links involving this sphere
                        links.discard(frozenset((selected.id,)))
                        to_remove = {lnk for lnk in links if selected.id in lnk}
                        links -= to_remove
                        selected_set.discard(selected)
                        selected.cleanup(); spheres.remove(selected); selected = None

            elif event.type == MOUSEBUTTONDOWN:
                in_banner = event.pos[1] < BANNER_H
                shift = pygame.key.get_mods() & KMOD_SHIFT

                # Check dropdown first
                if event.button == 1 and dropdown.hit_test(event.pos[0], event.pos[1]):
                    if selected and not selected.is_image:
                        selected.font_size = dropdown.current_size
                        selected._rebuild_texture()
                    continue

                if event.button == 1 and not in_banner:
                    dragged = False; last_mouse = event.pos; camera.apply()
                    hit = pick_sphere(spheres, event.pos[0], event.pos[1], camera)
                    if hit is not None:
                        if shift:
                            # Shift+click: toggle in multi-select set
                            if hit in selected_set:
                                selected_set.discard(hit)
                                if selected is hit:
                                    selected = next(iter(selected_set), None)
                            else:
                                selected_set.add(hit)
                                selected = hit
                        else:
                            # Normal click: single select
                            selected = hit
                            selected_set = {hit}
                        dragging_sphere = hit
                        drag_depth = project_depth(hit.pos)
                        mouse_down_left = False
                    else:
                        if not shift:
                            selected = None; selected_set.clear()
                        mouse_down_left = True

                elif event.button == 3 and not in_banner:
                    mouse_down_right = True; last_mouse = event.pos

                elif event.button == 4: camera.zoom(3)
                elif event.button == 5: camera.zoom(-3)

            elif event.type == MOUSEBUTTONUP:
                if event.button == 1:
                    if dragging_sphere is not None:
                        dragging_sphere = None; drag_depth = None
                    if mouse_down_left and not dragged:
                        camera.apply()
                        hit = pick_sphere(spheres, event.pos[0], event.pos[1], camera)
                        shift = pygame.key.get_mods() & KMOD_SHIFT
                        if hit is not None:
                            if shift:
                                if hit in selected_set:
                                    selected_set.discard(hit)
                                    if selected is hit:
                                        selected = next(iter(selected_set), None)
                                else:
                                    selected_set.add(hit)
                                    selected = hit
                            else:
                                selected = hit
                                selected_set = {hit}
                        else:
                            if not shift:
                                selected = None; selected_set.clear()
                    mouse_down_left = False
                elif event.button == 3:
                    mouse_down_right = False

            elif event.type == MOUSEMOTION:
                mx, my = event.pos
                dx = mx - last_mouse[0]; dy = my - last_mouse[1]
                if dragging_sphere is not None and drag_depth is not None:
                    camera.apply()
                    wx, wy, wz = unproject_at_depth(mx, my, drag_depth)
                    dragging_sphere.pos = [wx, wy, wz]; dragged = True
                elif mouse_down_left and abs(dx) + abs(dy) > 2:
                    dragged = True; camera.orbit(dx, dy)
                if mouse_down_right:
                    camera.pan(dx, dy)
                last_mouse = event.pos

        # ── 3-D render ────────────────────────────────────────────────────────
        glClearColor(0.85, 0.85, 0.87, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        camera.apply(); draw_grid()
        draw_links(spheres)
        for sp in spheres:
            sp.draw(sp in selected_set)

        # ── 2-D overlay ───────────────────────────────────────────────────────
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
        glOrtho(0, WIN_W, WIN_H, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        glDisable(GL_DEPTH_TEST); glDisable(GL_LIGHTING); glEnable(GL_BLEND)

        hud_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        hud.draw(hud_surf, spheres, selected, cursor_visible)
        glRasterPos2i(0, 0)
        glDrawPixels(WIN_W, WIN_H, GL_RGBA, GL_UNSIGNED_BYTE,
                     pygame.image.tostring(hud_surf, "RGBA", True))

        banner.draw()
        sidebar.draw()
        dropdown.draw_gl()

        glEnable(GL_DEPTH_TEST); glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION); glPopMatrix()
        glMatrixMode(GL_MODELVIEW); glPopMatrix()
        pygame.display.flip()

    for sp in spheres: sp.cleanup()
    banner.free(); sidebar.free(); pygame.quit()


if __name__ == "__main__":
    main()
