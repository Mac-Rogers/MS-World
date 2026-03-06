"""
Sphere Text - 3D navigable spheres with editable text
Requirements: pip install pygame PyOpenGL PyOpenGL_accelerate numpy
"""

import sys
import math
import textwrap
import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

# ── Constants ────────────────────────────────────────────────────────────────
WIN_W, WIN_H = 1200, 800
FPS = 60
BASE_RADIUS = 1.5
RADIUS_PER_CHAR = 0.012
MAX_RADIUS = 4.5
FONT_SIZE = 100

COLORS = [
    ((0.20, 0.20, 0.20), (1.0, 1.0, 1.0)),      # dark gray text on white
    ((0.30, 0.30, 0.30), (0.95, 0.95, 0.95)),   # dark gray text on light gray
    ((0.25, 0.25, 0.25), (0.98, 0.98, 0.98)),   # charcoal on off-white
    ((0.15, 0.15, 0.15), (0.93, 0.93, 0.93)),   # near-black on pale gray
    ((0.35, 0.35, 0.35), (0.97, 0.97, 0.97)),   # medium gray on bright white
]


# ── Sphere ───────────────────────────────────────────────────────────────────
class Sphere:
    _id_counter = 0

    def __init__(self, position, color_idx=0):
        Sphere._id_counter += 1
        self.id = Sphere._id_counter
        self.pos = list(position)
        self.text = ""
        self.color_idx = color_idx % len(COLORS)
        self.texture_id = None
        self.quadric = gluNewQuadric()
        gluQuadricTexture(self.quadric, GL_TRUE)
        gluQuadricNormals(self.quadric, GLU_SMOOTH)
        self._rebuild_texture()
        # no spin
        self.spin = 0.0
        self.angle = 0.0

    @property
    def radius(self):
        # Calculate how many characters fit in the current texture width
        chars_per_line = max(50, int(2048 / (FONT_SIZE * 0.55)))
        # Only expand if text would need more lines than fit in texture height
        text_lines = max(1, len(self.text) // chars_per_line)
        # Start expanding after 4 lines
        max_lines = 4
        
        if text_lines > max_lines:
            # Only grow if we exceed 4 lines
            r = BASE_RADIUS + (text_lines - max_lines) * RADIUS_PER_CHAR * 10
        else:
            r = BASE_RADIUS
        
        return min(r, MAX_RADIUS)

    def add_char(self, ch):
        self.text += ch
        self._rebuild_texture()

    def backspace(self):
        if self.text:
            self.text = self.text[:-1]
            self._rebuild_texture()

    def _rebuild_texture(self):
        text_color, bg_color = COLORS[self.color_idx]
        # Wide texture wraps horizontally around sphere with multiple bands
        width = 2048
        height = 512
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        bg = tuple(int(c * 255) for c in bg_color)
        surf.fill((*bg, 255))

        font = pygame.font.SysFont("monospace", FONT_SIZE, bold=True)
        # More characters per line for horizontal wrapping
        chars_per_line = max(50, int(width / (FONT_SIZE * 0.55)))
        display = self.text if self.text else "[ empty ]"
        lines = textwrap.wrap(display, width=chars_per_line) or [display]

        tc = tuple(int(c * 255) for c in text_color)
        line_h = FONT_SIZE + 8
        total_h = len(lines) * line_h
        y = (height - total_h) // 2

        for line in lines:
            rendered = font.render(line, True, tc)
            x = 20  # Left-align for horizontal reading
            surf.blit(rendered, (x, y))
            y += line_h

        self._upload_texture(surf)

    def _upload_texture(self, surf):
        if self.texture_id is not None:
            glDeleteTextures([self.texture_id])
        data = pygame.image.tostring(surf, "RGBA", True)
        tid = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tid)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        # Horizontal wrap around sphere (longitude): repeat S
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        # No vertical wrap (latitude): clamp T
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_RGBA, surf.get_width(), surf.get_height(),
            0, GL_RGBA, GL_UNSIGNED_BYTE, data
        )
        self.texture_id = tid

    def draw(self, selected):
        glPushMatrix()
        glTranslatef(*self.pos)
        glRotatef(self.angle, 0, 1, 0)

        r = self.radius

        # Outer glow ring if selected
        if selected:
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_LIGHTING)
            glColor4f(0.91, 0.30, 0.16, 0.6)
            glLineWidth(2.5)
            self._draw_circle(r + 0.08, 80)
            glRotatef(90, 1, 0, 0)
            self._draw_circle(r + 0.08, 80)
            glRotatef(-90, 1, 0, 0)
            glLineWidth(1.0)
            glEnable(GL_LIGHTING)
            glEnable(GL_TEXTURE_2D)

        # Sphere (default UV mapping = horizontal wrap around longitude)
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
        if self.texture_id:
            glDeleteTextures([self.texture_id])
        gluDeleteQuadric(self.quadric)


# ── Camera / Orbit ────────────────────────────────────────────────────────────
class Camera:
    def __init__(self):
        self.theta = 0.3        # horizontal angle
        self.phi = 1.2          # vertical angle
        self.radius = 18.0
        self.target = [0.0, 0.0, 0.0]

    def apply(self):
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        eye = self._eye()
        gluLookAt(eye[0], eye[1], eye[2],
                  self.target[0], self.target[1], self.target[2],
                  0, 1, 0)

    def _eye(self):
        x = self.target[0] + self.radius * math.sin(self.phi) * math.sin(self.theta)
        y = self.target[1] + self.radius * math.cos(self.phi)
        z = self.target[2] + self.radius * math.sin(self.phi) * math.cos(self.theta)
        return (x, y, z)

    def orbit(self, dx, dy):
        self.theta -= dx * 0.007
        self.phi = max(0.15, min(math.pi - 0.15, self.phi + dy * 0.007))

    def pan(self, dx, dy):
        # right vector
        rx = math.cos(self.theta)
        rz = -math.sin(self.theta)
        # up vector (approx)
        ux = math.cos(self.phi) * math.sin(self.theta)
        uy = -math.sin(self.phi)
        uz = math.cos(self.phi) * math.cos(self.theta)
        scale = self.radius * 0.001
        self.target[0] += (-dx * rx + dy * ux) * scale
        self.target[1] += dy * uy * scale
        self.target[2] += (-dx * rz + dy * uz) * scale

    def zoom(self, delta):
        self.radius = max(3, min(80, self.radius - delta * 0.8))

    def look_at(self, pos, radius):
        self.target = list(pos)
        self.radius = radius * 4.5


# ── Picking ───────────────────────────────────────────────────────────────────
def pick_sphere(spheres, mx, my, camera):
    """Ray-sphere intersection in world space."""
    # Reconstruct projection + modelview
    proj = glGetDoublev(GL_PROJECTION_MATRIX)
    mv = glGetDoublev(GL_MODELVIEW_MATRIX)
    vp = glGetIntegerv(GL_VIEWPORT)

    # Two points on the ray
    near = gluUnProject(mx, WIN_H - my, 0.0, mv, proj, vp)
    far  = gluUnProject(mx, WIN_H - my, 1.0, mv, proj, vp)

    ro = np.array(near)
    rd = np.array(far) - ro
    rd /= np.linalg.norm(rd)

    best, best_t = None, 1e18
    for s in spheres:
        oc = ro - np.array(s.pos)
        b = np.dot(oc, rd)
        c = np.dot(oc, oc) - s.radius ** 2
        disc = b * b - c
        if disc >= 0:
            t = -b - math.sqrt(disc)
            if 0 < t < best_t:
                best_t = t
                best = s
    return best


# ── HUD ───────────────────────────────────────────────────────────────────────
class HUD:
    def __init__(self):
        self.font_big = pygame.font.SysFont("monospace", 14, bold=True)
        self.font_sm  = pygame.font.SysFont("monospace", 12)
        self.surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        
        # Load banner image
        try:
            self.banner = pygame.image.load("banner.png").convert_alpha()
        except:
            self.banner = None

    def draw(self, screen, spheres, selected, cursor_visible):
        self.surf.fill((0, 0, 0, 0))

        # Title
        title = self.font_big.render("Microsoft World", True, (240, 236, 227))
        self.surf.blit(title, (16, 12))
        sub = self.font_sm.render("drag=orbit  right-drag=pan  scroll=zoom  click=select  n=new sphere  del=delete", True, (100, 96, 90))
        self.surf.blit(sub, (16, 32))

        # Sphere list
        y = 70
        self.surf.blit(self.font_sm.render("SPHERES", True, (100, 96, 90)), (16, y)); y += 18
        for s in spheres:
            active = s is selected
            col = (232, 77, 42) if active else (180, 175, 165)
            preview = s.text[:20] + ("…" if len(s.text) > 20 else "") if s.text else "[ empty ]"
            label = f"● #{s.id}  {preview}"
            txt = self.font_sm.render(label, True, col)
            self.surf.blit(txt, (16, y)); y += 18

        # Selected info
        if selected:
            info = f"Selected: #{selected.id}  |  {len(selected.text)} chars  |  R={selected.radius:.2f}"
            txt = self.font_sm.render(info, True, (232, 77, 42))
            self.surf.blit(txt, (16, WIN_H - 50))

            # Show typed text with cursor
            display = selected.text + ("|" if cursor_visible else " ")
            # Split into last 3 lines visible
            chars_per = 80
            lines = textwrap.wrap(display, chars_per) or [display]
            for i, line in enumerate(lines[-3:]):
                t = self.font_sm.render(line, True, (200, 200, 200))
                self.surf.blit(t, (16, WIN_H - 30 + i * 14 - (len(lines[-3:]) - 1) * 14))
        else:
            hint = self.font_sm.render("Click a sphere to select it, then type", True, (90, 86, 80))
            self.surf.blit(hint, (16, WIN_H - 30))

        # Draw HUD to screen
        screen.blit(self.surf, (0, 0))
        
        # Draw banner on top
        if self.banner:
            screen.blit(self.banner, (0, 0))


# ── Main ──────────────────────────────────────────────────────────────────────
def setup_gl():
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)

    glLightfv(GL_LIGHT0, GL_POSITION, [8.0, 12.0, 10.0, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.0, 0.85, 0.7, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])

    glLightfv(GL_LIGHT1, GL_POSITION, [-6.0, -4.0, -8.0, 1.0])
    glLightfv(GL_LIGHT1, GL_DIFFUSE,  [0.2, 0.3, 0.5, 1.0])

    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.15, 0.15, 0.18, 1.0])

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(55, WIN_W / WIN_H, 0.1, 200)
    glMatrixMode(GL_MODELVIEW)


def draw_grid():
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glColor4f(0.15, 0.15, 0.2, 0.6)
    glLineWidth(1.0)
    glBegin(GL_LINES)
    size = 30
    step = 2
    y = -6
    for i in range(-size, size + 1, step):
        glVertex3f(i, y, -size); glVertex3f(i, y, size)
        glVertex3f(-size, y, i); glVertex3f(size, y, i)
    glEnd()
    glEnable(GL_LIGHTING)


def new_sphere_position(spheres):
    """Spread new spheres out."""
    angle = len(spheres) * 137.5  # golden angle
    r = 4 + len(spheres) * 0.5
    x = math.cos(math.radians(angle)) * r
    z = math.sin(math.radians(angle)) * r
    y = (len(spheres) % 3 - 1) * 2.0
    return (x, y, z)


def project_depth(world_pos):
    """Return window-space depth (0..1) for a world position."""
    proj = glGetDoublev(GL_PROJECTION_MATRIX)
    mv = glGetDoublev(GL_MODELVIEW_MATRIX)
    vp = glGetIntegerv(GL_VIEWPORT)
    wx, wy, wz = gluProject(world_pos[0], world_pos[1], world_pos[2], mv, proj, vp)
    return wz


def unproject_at_depth(mx, my, depth):
    """Convert mouse x/y + depth back to world position."""
    proj = glGetDoublev(GL_PROJECTION_MATRIX)
    mv = glGetDoublev(GL_MODELVIEW_MATRIX)
    vp = glGetIntegerv(GL_VIEWPORT)
    return gluUnProject(mx, WIN_H - my, depth, mv, proj, vp)


def main():
    pygame.init()
    pygame.display.set_mode((WIN_W, WIN_H), DOUBLEBUF | OPENGL)
    pygame.display.set_caption("MS World")
    pygame.key.set_repeat(400, 50)

    setup_gl()

    camera = Camera()
    hud = HUD()
    spheres = []
    selected = None
    color_idx = 0

    # Starter sphere
    s = Sphere((0, 0, 0), color_idx)
    s.text = "Hello world"
    s._rebuild_texture()
    spheres.append(s)

    mouse_down_left = False
    mouse_down_right = False
    last_mouse = (0, 0)
    dragged = False

    # NEW: sphere dragging state
    dragging_sphere = None
    drag_depth = None

    clock = pygame.time.Clock()
    cursor_timer = 0
    cursor_visible = True

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        cursor_timer += dt
        if cursor_timer > 0.5:
            cursor_timer = 0
            cursor_visible = not cursor_visible

        # Spin spheres
        # for sp in spheres:
        #     sp.angle += sp.spin * dt

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False

            elif event.type == KEYDOWN:
                if selected:
                    if event.key == K_BACKSPACE:
                        selected.backspace()
                    elif event.key == K_RETURN:
                        selected.add_char('\n')
                    elif event.key == K_ESCAPE:
                        selected = None
                    elif event.key == K_n:
                        pass  # fall through to global n
                    elif event.unicode and event.unicode.isprintable():
                        selected.add_char(event.unicode)

                if event.key == K_n:
                    pos = new_sphere_position(spheres)
                    sp = Sphere(pos, color_idx % len(COLORS))
                    color_idx += 1
                    spheres.append(sp)
                    selected = sp
                    camera.look_at(pos, sp.radius)
                elif event.key == K_DELETE or event.key == K_BACKSPACE:
                    if selected and not selected.text:
                        selected.cleanup()
                        spheres.remove(selected)
                        selected = None

            elif event.type == MOUSEBUTTONDOWN:
                if event.button == 1:
                    dragged = False
                    last_mouse = event.pos

                    # Use current camera matrices for picking/projection
                    camera.apply()
                    hit = pick_sphere(spheres, event.pos[0], event.pos[1], camera)

                    if hit is not None:
                        selected = hit
                        dragging_sphere = hit
                        drag_depth = project_depth(hit.pos)
                        mouse_down_left = False  # do not orbit when dragging sphere
                    else:
                        mouse_down_left = True   # orbit mode when empty space clicked

                elif event.button == 3:
                    mouse_down_right = True
                    last_mouse = event.pos
                elif event.button == 4:
                    camera.zoom(3)
                elif event.button == 5:
                    camera.zoom(-3)

            elif event.type == MOUSEBUTTONUP:
                if event.button == 1:
                    # Stop sphere drag
                    if dragging_sphere is not None:
                        dragging_sphere = None
                        drag_depth = None

                    # Stop orbit mode
                    if mouse_down_left and not dragged:
                        camera.apply()
                        hit = pick_sphere(spheres, event.pos[0], event.pos[1], camera)
                        selected = hit
                    mouse_down_left = False

                elif event.button == 3:
                    mouse_down_right = False

            elif event.type == MOUSEMOTION:
                mx, my = event.pos
                lx, ly = last_mouse
                dx, dy = mx - lx, my - ly

                # Drag selected sphere in screen plane (at captured depth)
                if dragging_sphere is not None and drag_depth is not None:
                    camera.apply()
                    wx, wy, wz = unproject_at_depth(mx, my, drag_depth)
                    dragging_sphere.pos[0] = wx
                    dragging_sphere.pos[1] = wy
                    dragging_sphere.pos[2] = wz
                    dragged = True

                # Otherwise normal camera controls
                elif mouse_down_left and (abs(dx) + abs(dy)) > 2:
                    dragged = True
                    camera.orbit(dx, dy)

                if mouse_down_right:
                    camera.pan(dx, dy)

                last_mouse = event.pos

        # ── Render ────────────────────────────────────────────────────────────
        glClearColor(0.85, 0.85, 0.87, 1.0)  # Light gray background
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        camera.apply()

        draw_grid()

        for sp in spheres:
            sp.draw(sp is selected)

        # HUD overlay via pygame surface
        pygame.display.get_surface()  # ensure surface exists
        # Switch to 2D for HUD
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity()
        glOrtho(0, WIN_W, WIN_H, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        glDisable(GL_DEPTH_TEST); glDisable(GL_LIGHTING)

        # Blit HUD surface via pixel transfer
        hud_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        hud.draw(hud_surf, spheres, selected, cursor_visible)
        hud_data = pygame.image.tostring(hud_surf, "RGBA", True)
        glEnable(GL_BLEND)
        glRasterPos2i(0, 0)
        glDrawPixels(WIN_W, WIN_H, GL_RGBA, GL_UNSIGNED_BYTE, hud_data)

        glEnable(GL_DEPTH_TEST); glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION); glPopMatrix()
        glMatrixMode(GL_MODELVIEW); glPopMatrix()

        pygame.display.flip()

    for sp in spheres:
        sp.cleanup()
    pygame.quit()


if __name__ == "__main__":
    main()
