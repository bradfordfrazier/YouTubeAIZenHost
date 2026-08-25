"""
GPU-Accelerated 1920x1080 @ 60 FPS Visualizer Canvas for AI Live Stream Co-Host.
Features dynamic mood-driven particle/gradient background shaders,
audio spectrum FFT & hologram core reactivity, and glassmorphism broadcast HUD overlays.
"""

import math
import os
import random
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pygame

from config import config

# Set SDL to avoid window popups in headless mode if requested
if config.visualizer_headless:
    os.environ["SDL_VIDEODRIVER"] = "dummy"


class ColorPalette:
    """Dynamic color schemes for mood states."""
    PALETTES = {
        "chill": {
            "bg_dark": (10, 16, 32),
            "bg_accent": (20, 45, 85),
            "primary": (0, 200, 255),
            "secondary": (70, 110, 240),
            "highlight": (180, 240, 255),
            "glow": (0, 180, 255, 60),
            "speed": 0.6,
        },
        "energetic": {
            "bg_dark": (18, 12, 30),
            "bg_accent": (65, 25, 80),
            "primary": (255, 140, 0),
            "secondary": (0, 240, 255),
            "highlight": (255, 220, 100),
            "glow": (255, 120, 0, 75),
            "speed": 1.4,
        },
        "hyped": {
            "bg_dark": (22, 8, 35),
            "bg_accent": (80, 10, 90),
            "primary": (255, 20, 147),
            "secondary": (0, 255, 240),
            "highlight": (255, 255, 255),
            "glow": (255, 0, 180, 90),
            "speed": 2.0,
        },
        "mysterious": {
            "bg_dark": (8, 20, 22),
            "bg_accent": (15, 55, 45),
            "primary": (0, 255, 170),
            "secondary": (138, 43, 226),
            "highlight": (180, 255, 230),
            "glow": (0, 255, 150, 60),
            "speed": 0.7,
        },
        "thoughtful": {
            "bg_dark": (16, 18, 30),
            "bg_accent": (45, 40, 75),
            "primary": (245, 190, 60),
            "secondary": (90, 120, 220),
            "highlight": (255, 240, 180),
            "glow": (240, 180, 50, 60),
            "speed": 0.8,
        },
        "snarky": {
            "bg_dark": (18, 22, 16),
            "bg_accent": (45, 60, 25),
            "primary": (180, 255, 0),
            "secondary": (220, 40, 255),
            "highlight": (230, 255, 150),
            "glow": (180, 255, 0, 75),
            "speed": 1.3,
        },
        "transcendent": {
            "bg_dark": (12, 10, 28),
            "bg_accent": (40, 20, 70),
            "primary": (255, 215, 0),
            "secondary": (186, 85, 211),
            "highlight": (255, 250, 220),
            "glow": (255, 215, 0, 80),
            "speed": 0.6,
        },
    }

    @classmethod
    def get(cls, mood: str) -> Dict:
        return cls.PALETTES.get(mood.lower(), cls.PALETTES["energetic"])


class Particle:
    """Floating ambient background particle node reacting to mood speed and audio energy."""
    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.reset(random_y=True)

    def reset(self, random_y: bool = False):
        self.x = random.uniform(0, self.w)
        self.y = random.uniform(0, self.h) if random_y else self.h + random.uniform(10, 50)
        self.size = random.uniform(2.0, 5.5)
        self.base_speed = random.uniform(0.4, 1.8)
        self.angle = random.uniform(0, math.pi * 2)
        self.osc_speed = random.uniform(0.02, 0.06)
        self.alpha = random.randint(50, 200)

    def update(self, speed_mult: float, energy: float):
        self.angle += self.osc_speed
        self.y -= (self.base_speed * speed_mult) + (energy * 4.0)
        self.x += math.sin(self.angle) * 0.8
        if self.y < -20 or self.x < -20 or self.x > self.w + 20:
            self.reset(random_y=False)


class CelestialSparkle:
    """Orbiting radiant photon / diamond sparkle orbiting the central point of light."""
    def __init__(self, cx: int, cy: int):
        self.cx = cx
        self.cy = cy
        self.reset()

    def reset(self):
        self.radius_x = random.uniform(25, 210)
        self.radius_y = self.radius_x * random.uniform(0.35, 0.75)
        self.tilt = random.uniform(-0.6, 0.6)
        self.angle = random.uniform(0, math.pi * 2)
        self.speed = random.uniform(0.015, 0.045) * random.choice([-1, 1])
        self.size = random.uniform(1.5, 4.2)
        self.base_alpha = random.randint(110, 240)
        self.phase = random.uniform(0, math.pi * 2)

    def update(self, dt: float, rms: float):
        self.angle += self.speed * (1.0 + rms * 3.5)
        self.phase += 0.09

    def get_pos(self) -> Tuple[int, int]:
        x_raw = math.cos(self.angle) * self.radius_x
        y_raw = math.sin(self.angle) * self.radius_y
        x = self.cx + int(x_raw * math.cos(self.tilt) - y_raw * math.sin(self.tilt))
        y = self.cy + int(x_raw * math.sin(self.tilt) + y_raw * math.cos(self.tilt))
        return x, y

    def get_alpha(self, rms: float) -> int:
        shimmer = 0.55 + 0.45 * math.sin(self.phase)
        return min(255, int(self.base_alpha * shimmer + rms * 70))


class CelebrationParticle:
    """Radiant fireworks / celestial confetti particle for celebration events."""
    def __init__(self, cx: int, cy: int, max_w: int = 1920, max_h: int = 1080):
        self.cx = cx
        self.cy = cy
        self.max_w = max_w
        self.max_h = max_h
        self.reset()

    def reset(self):
        self.x = float(self.cx + random.uniform(-50, 50))
        self.y = float(self.cy + random.uniform(-50, 50))
        speed = random.uniform(7.0, 24.0)
        angle = random.uniform(0, math.pi * 2)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(4.0, 10.0)  # Upward fountain burst
        self.gravity = random.uniform(0.25, 0.42)
        self.drag = random.uniform(0.96, 0.98)
        self.size = random.uniform(3.5, 9.0)
        self.rotation = random.uniform(0, math.pi * 2)
        self.rot_speed = random.uniform(-0.20, 0.20)
        self.color = random.choice([
            (255, 220, 40),   # Radiant Gold
            (255, 255, 255),  # Pure White Diamond
            (255, 70, 180),   # Neon Magenta
            (0, 245, 255),    # Electric Cyan
            (255, 145, 20),   # Sunfire Amber
            (185, 100, 255),  # Cosmic Violet
            (60, 255, 160),   # Emerald Aurora
        ])
        self.alpha = 255.0
        self.fade_rate = random.uniform(1.2, 2.8)
        self.is_alive = True
        self.shape = random.choice(["circle", "diamond", "ribbon"])

    def update(self):
        if not self.is_alive:
            return
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.vx *= self.drag
        self.vy *= self.drag
        self.rotation += self.rot_speed
        self.alpha -= self.fade_rate
        if self.alpha <= 0 or self.y > self.max_h + 80 or self.x < -100 or self.x > self.max_w + 100:
            self.is_alive = False


class Visualizer:
    """
    Broadcast visualizer renderer with dual aspect ratio support:
    - 16:9 Landscape (1920x1080 @ 60 FPS)
    - 9:16 Vertical / Mobile (1080x1920 @ 60 FPS)
    """

    def __init__(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        window_width: Optional[int] = None,
        window_height: Optional[int] = None,
    ):
        self.cfg = config
        self.width = width or self.cfg.visualizer_width  # 1920 (16:9) or 1080 (9:16)
        self.height = height or self.cfg.visualizer_height  # 1080 (16:9) or 1920 (9:16)
        self.fps = self.cfg.visualizer_fps  # 60
        self.cohost_name = self.cfg.ai_cohost_name
        self.is_vertical = (self.height > self.width)

        pygame.init()
        pygame.font.init()

        self.should_quit = False
        if self.cfg.visualizer_headless:
            self.window_surf = None
            self.screen = pygame.Surface((self.width, self.height))
            self.window_size = (self.width, self.height)
        else:
            default_win_w = 450 if self.is_vertical else 1280
            default_win_h = 800 if self.is_vertical else 720
            win_w = window_width or int(os.getenv("VISUALIZER_WINDOW_WIDTH", str(default_win_w)))
            win_h = window_height or int(os.getenv("VISUALIZER_WINDOW_HEIGHT", str(default_win_h)))
            self.window_size = (win_w, win_h)
            self.window_surf = pygame.display.set_mode(self.window_size, pygame.DOUBLEBUF | pygame.RESIZABLE)
            pygame.event.set_grab(False)
            pygame.mouse.set_visible(True)
            caption_mode = "Vertical 9:16 (1080x1920)" if self.is_vertical else "Landscape 16:9 (1920x1080)"
            pygame.display.set_caption(f"AI Co-Host Broadcast Visualizer - {caption_mode}")
            # Internal full-resolution rendering surface (always full 1080x1920 or 1920x1080 for NDI)
            self.screen = pygame.Surface((self.width, self.height))

        self.clock = pygame.time.Clock()

        # Fonts
        self.font_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 24, bold=True)
        self.font_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 20)
        self.font_ai_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 26)
        self.font_host_transcript = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 22)
        self.font_small = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 15)
        self.font_badge = pygame.font.SysFont("Consolas, Segoe UI, sans-serif", 14, bold=True)
        self.font_chat_author = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 19, bold=True)
        self.font_chat_msg = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 18)
        self.font_god_badge = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 18, bold=True)
        self.font_callout_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 32, bold=True)
        self.font_callout_sub = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 20)
        self.font_callout_tag = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 15, bold=True)
        self.font_callout_icon = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 28, bold=True)

        # Ambient Particle System
        self.num_particles = 120
        self.particles = [Particle(self.width, self.height) for _ in range(self.num_particles)]

        # Celestial Sparkle System around the central Point of Light
        self.core_cx = self.width // 2
        self.core_cy = 440 if self.is_vertical else 430
        self.num_sparkles = 40
        self.celestial_sparkles = [
            CelestialSparkle(self.core_cx, self.core_cy) for _ in range(self.num_sparkles)
        ]

        # Celebration Fireworks & Confetti Burst System
        self.celebration_particles: List[CelebrationParticle] = []
        self.celebration_timer: float = 0.0

        # Promotional Callout Overlays ("Ask God Your Questions", "Like & Subscribe")
        self.promo_enabled = getattr(self.cfg, "promo_overlay_enabled", True)
        self.promo_interval = getattr(self.cfg, "promo_overlay_interval_sec", 40.0)
        self.promo_duration = getattr(self.cfg, "promo_overlay_duration_sec", 10.0)
        self.promo_state = "off"  # "off", "entrance", "display", "exit"
        self.promo_timer = self.promo_interval * 0.35  # First promo appears after a brief initial warmup
        self.promo_state_timer = 0.0
        self.promo_current_type = "ask_god"  # alternates: "ask_god" <-> "like_sub"
        self.promo_slide_factor = 0.0
        self.promo_alpha = 0.0

        # Scintillation glint seeds for glistening diamond twinkle
        random.seed(42)
        self.glint_seeds = [
            {
                "angle": i * (2 * math.pi / 12) + random.uniform(-0.2, 0.2),
                "dist": random.uniform(32, 110),
                "freq": random.uniform(4.5, 9.5),
                "phase": random.uniform(0, math.pi * 2),
                "size": random.uniform(8, 20),
            }
            for i in range(12)
        ]
        random.seed()

        # State tracking for smooth lerp transitions
        self.current_mood = "chill"
        self.target_mood = "chill"
        self.mood_lerp_factor = 1.0

        # Colors (interpolated)
        p = ColorPalette.get("chill")
        self.c_bg_dark = np.array(p["bg_dark"], dtype=float)
        self.c_bg_accent = np.array(p["bg_accent"], dtype=float)
        self.c_primary = np.array(p["primary"], dtype=float)
        self.c_secondary = np.array(p["secondary"], dtype=float)
        self.c_highlight = np.array(p["highlight"], dtype=float)

        self.time_elapsed = 0.0
        self.light_rotation = 0.0
        self.subtitle_display_text = ""
        self.subtitle_target_text = ""
        self.typewriter_index = 0

        # Pre-allocated scratch surfaces for 60+ FPS rendering performance
        self.box_size = 840
        self.surf_bloom = pygame.Surface((self.box_size, self.box_size), pygame.SRCALPHA)
        self.surf_flare = pygame.Surface((self.box_size, self.box_size), pygame.SRCALPHA)
        self.surf_particles = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.surf_waves = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.surf_glow = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.surf_celebration = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.surf_spec = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.surf_emblem = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self.surf_header = pygame.Surface((self.width, 60), pygame.SRCALPHA)

        # Adaptive card dimensions
        host_w, host_h = (1000, 140) if self.is_vertical else (560, 140)
        chat_w, chat_h = (1000, 700) if self.is_vertical else (400, 640)
        sub_w, sub_h = (1000, 280) if self.is_vertical else (1000, 240)
        promo_w, promo_h = (760, 146) if self.is_vertical else (760, 146)

        self.surf_host_card = pygame.Surface((host_w, host_h), pygame.SRCALPHA)
        self.surf_chat_card = pygame.Surface((chat_w, chat_h), pygame.SRCALPHA)
        self.surf_subtitle_card = pygame.Surface((sub_w, sub_h), pygame.SRCALPHA)
        self.surf_promo_card = pygame.Surface((promo_w, promo_h), pygame.SRCALPHA)

    def trigger_promo(self, promo_type: Optional[str] = None, duration: Optional[float] = None):
        """Triggers a fun promotional graphic overlay immediately ('ask_god' or 'like_sub')."""
        if promo_type in ("ask_god", "like_sub"):
            self.promo_current_type = promo_type
        if duration is not None and duration > 0:
            self.promo_duration = duration
        self.promo_state = "entrance"
        self.promo_state_timer = 0.0
        self.promo_slide_factor = 0.0
        self.promo_alpha = 0.0

    def trigger_celebration(self, duration: float = 5.0, count: int = 140):
        """Triggers a grand celestial fireworks and confetti shower across the stream."""
        self.celebration_timer = max(self.celebration_timer, duration)
        for _ in range(count):
            self.celebration_particles.append(CelebrationParticle(self.core_cx, self.core_cy, self.width, self.height))

    def set_mood(self, mood: str):
        """Update active mood."""
        if mood.lower() in ColorPalette.PALETTES and mood.lower() != self.target_mood:
            self.target_mood = mood.lower()
            self.mood_lerp_factor = 0.0

    def set_subtitle(self, text: str):
        """Update AI co-host speaking subtitle text."""
        if text != self.subtitle_target_text:
            self.subtitle_target_text = text
            self.typewriter_index = 0

    def _update_palette_lerp(self, dt: float):
        """Smoothly interpolate colors toward target mood."""
        if self.mood_lerp_factor < 1.0:
            self.mood_lerp_factor = min(1.0, self.mood_lerp_factor + dt * 1.5)
            target = ColorPalette.get(self.target_mood)
            alpha = self.mood_lerp_factor

            cur = ColorPalette.get(self.current_mood)
            for key, attr in [
                ("bg_dark", "c_bg_dark"),
                ("bg_accent", "c_bg_accent"),
                ("primary", "c_primary"),
                ("secondary", "c_secondary"),
                ("highlight", "c_highlight"),
            ]:
                c_start = np.array(cur[key], dtype=float)
                c_end = np.array(target[key], dtype=float)
                setattr(self, attr, c_start * (1.0 - alpha) + c_end * alpha)

            if self.mood_lerp_factor >= 1.0:
                self.current_mood = self.target_mood

    def render_frame(
        self,
        audio_metrics: Dict,
        chat_messages: List[Dict],
        host_transcript: str,
        ai_subtitle: str,
        host_connected: bool = True,
        obs_connected: bool = True,
        engagement_mode: str = "active",
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
    ) -> bytes:
        """
        Renders a full 1080p60 frame and returns the RGBA byte buffer.
        """
        dt = 1.0 / self.fps
        self.time_elapsed += dt
        self._update_palette_lerp(dt)
        self.set_subtitle(ai_subtitle)

        # Extract audio metrics
        rms = audio_metrics.get("rms", 0.0)
        spectrum = audio_metrics.get("spectrum", np.zeros(32, dtype=np.float32))
        is_speaking = audio_metrics.get("is_speaking", False)

        # 1. Background Gradient & Wave Ribbons
        self._draw_dynamic_background(rms)

        # 2. Particle Field
        p_info = ColorPalette.get(self.current_mood)
        speed_mult = p_info["speed"]
        self._draw_particles(speed_mult, rms)

        # 3. Brightly Glistening and Shining Point of Light (God / The Source) & FFT Spectrum
        self._draw_hologram_core(rms, spectrum, is_speaking)

        # 4. Celebration Fireworks & Confetti Shower
        self._draw_celebration_fx(dt)

        # 5. Glassmorphism HUD Overlays
        self._draw_top_header(
            host_connected=host_connected,
            obs_connected=obs_connected,
            engagement_mode=engagement_mode,
            concurrent_viewers=concurrent_viewers,
            is_stream_live=is_stream_live,
        )
        self._draw_host_transcript_card(host_transcript)
        self._draw_live_chat_card(chat_messages)
        self._draw_ai_subtitle_card(is_speaking)

        # 6. Periodic Fun Promotional Graphic Overlays ("Ask God" & "Like & Subscribe")
        self._draw_promo_callout_overlay(dt)

        # Update Pygame display if not headless
        if not self.cfg.visualizer_headless and self.window_surf is not None:
            # Handle window events (resize, quit, etc.)
            for event in pygame.event.get():
                if event.type == pygame.VIDEORESIZE:
                    self.window_size = (max(180, event.w), max(180, event.h))
                    self.window_surf = pygame.display.set_mode(self.window_size, pygame.DOUBLEBUF | pygame.RESIZABLE)
                    pygame.event.set_grab(False)
                    pygame.mouse.set_visible(True)
                elif event.type == pygame.QUIT:
                    self.should_quit = True

            # Scale the high-res render canvas to the desktop window container
            if self.window_size == (self.width, self.height):
                self.window_surf.blit(self.screen, (0, 0))
            else:
                pygame.transform.scale(self.screen, self.window_size, self.window_surf)
            pygame.display.flip()

        # Return full pristine RGBA buffer for NDI (always 1080x1920 or 1920x1080)
        return pygame.image.tobytes(self.screen, "RGBA")

    def _draw_celebration_fx(self, dt: float):
        """Draws radiant fireworks and celestial confetti particles during celebration events."""
        if self.celebration_timer > 0:
            self.celebration_timer = max(0.0, self.celebration_timer - dt)
            # Continually spawn sparkle fountains while celebration timer is active
            if random.random() < 0.35:
                for _ in range(4):
                    self.celebration_particles.append(CelebrationParticle(self.core_cx, self.core_cy))

        if not self.celebration_particles:
            return

        self.surf_celebration.fill((0, 0, 0, 0))
        alive_particles = []

        for p in self.celebration_particles:
            p.update()
            if p.is_alive and p.alpha > 5:
                alive_particles.append(p)
                col = (*p.color, int(p.alpha))
                ix, iy = int(p.x), int(p.y)
                sz = max(2, int(p.size))

                if p.shape == "circle":
                    pygame.draw.circle(self.surf_celebration, col, (ix, iy), sz)
                elif p.shape == "diamond":
                    pts = [
                        (ix, iy - sz),
                        (ix + sz, iy),
                        (ix, iy + sz),
                        (ix - sz, iy),
                    ]
                    pygame.draw.polygon(self.surf_celebration, col, pts)
                else:  # ribbon
                    w = int(sz * 1.6)
                    h = max(2, int(sz * 0.6))
                    cos_r = math.cos(p.rotation)
                    sin_r = math.sin(p.rotation)
                    pts = [
                        (ix - w * cos_r + h * sin_r, iy - w * sin_r - h * cos_r),
                        (ix + w * cos_r + h * sin_r, iy + w * sin_r - h * cos_r),
                        (ix + w * cos_r - h * sin_r, iy + w * sin_r + h * cos_r),
                        (ix - w * cos_r - h * sin_r, iy - w * sin_r + h * cos_r),
                    ]
                    pygame.draw.polygon(self.surf_celebration, col, pts)

        self.celebration_particles = alive_particles
        self.screen.blit(self.surf_celebration, (0, 0), special_flags=pygame.BLEND_ADD)

    # --------------------------------------------------------------------------
    # Drawing Components
    # --------------------------------------------------------------------------
    def _draw_dynamic_background(self, rms: float):
        """Draws fluid dynamic gradient backdrop and subtle undulating energy waves."""
        c_top = tuple(int(c) for c in self.c_bg_dark)
        c_bot = tuple(int(c) for c in self.c_bg_accent)

        # Vertical background fill
        self.screen.fill(c_top)

        # Ambient radial glow behind the center point of light
        self.surf_glow.fill((0, 0, 0, 0))
        center_x, center_y = self.core_cx, self.core_cy
        radius = int(380 + rms * 320)
        c_prim = tuple(int(c) for c in self.c_primary)
        pygame.draw.circle(
            self.surf_glow,
            (*c_prim, int(30 + rms * 50)),
            (center_x, center_y),
            radius,
        )
        self.screen.blit(self.surf_glow, (0, 0))

        # Flowing sine wave ribbons in lower half
        self.surf_waves.fill((0, 0, 0, 0))
        num_waves = 3
        base_y_start = 1450 if self.is_vertical else 650
        y_step = 80 if self.is_vertical else 60
        for w_idx in range(num_waves):
            pts = []
            freq = 0.003 + w_idx * 0.0015
            phase = self.time_elapsed * (1.2 + w_idx * 0.4)
            amp = 25.0 + w_idx * 15.0 + rms * 60.0
            base_y = base_y_start + w_idx * y_step

            for x in range(0, self.width + 20, 20):
                y = base_y + math.sin(x * freq + phase) * amp + math.cos(x * 0.001 - phase * 0.5) * 15
                pts.append((x, int(y)))

            if len(pts) > 1:
                c_sec = tuple(int(c) for c in self.c_secondary)
                alpha = int(40 + w_idx * 20 + rms * 40)
                pygame.draw.lines(self.surf_waves, (*c_sec, alpha), False, pts, 2)

        self.screen.blit(self.surf_waves, (0, 0))

    def _draw_particles(self, speed_mult: float, rms: float):
        """Update and draw ambient floating particles."""
        self.surf_particles.fill((0, 0, 0, 0))
        c_high = tuple(int(c) for c in self.c_highlight)

        for p in self.particles:
            p.update(speed_mult, rms)
            alpha = min(255, int(p.alpha + rms * 100))
            pygame.draw.circle(self.surf_particles, (*c_high, alpha), (int(p.x), int(p.y)), int(p.size))

        self.screen.blit(self.surf_particles, (0, 0))

    def _draw_hologram_core(self, rms: float, spectrum: np.ndarray, is_speaking: bool):
        """
        Draws the central massive star shining in the distance:
        - Deep multi-stage celestial corona and heliosphere (calm when idle, reactive when speaking)
        - Audio-reactive acoustic shockwave ripple rings when speaking
        - 16-point space-telescope astronomical starburst diffraction spikes with smooth crystalline shimmer
        - Slender anamorphic horizontal equator flare streak
        - Orbiting celestial sparkle photons & scintillation glints
        - Pure white-hot solar photosphere & singularity nucleus
        - Center-aligned symmetrical crystal equalizer bars flanking the star (at cy)
        - Lowered celestial monogram badge.
        """
        cx, cy = self.core_cx, self.core_cy
        dt = 1.0 / self.fps
        self.light_rotation += 0.003 + (rms * 0.04 if is_speaking else 0.0)

        c_prim = tuple(int(c) for c in self.c_primary)
        c_sec = tuple(int(c) for c in self.c_secondary)
        c_high = tuple(int(c) for c in self.c_highlight)
        c_pure_white = (255, 255, 255)
        c_gold_white = (255, 250, 230)

        # Speaking intensity factor for exaggerated reactivity
        speak_boost = (rms * 2.5 + 0.3) if is_speaking else (rms * 1.0)

        # Local bounding box for high-performance additive surface blending
        box_size = self.box_size
        half_box = box_size // 2
        box_x = cx - half_box
        box_y = cy - half_box
        lx, ly = half_box, half_box  # Local center within box

        # ----------------------------------------------------------------------
        # 1. Massive Stellar Atmosphere, Corona & Acoustic Shockwaves
        # ----------------------------------------------------------------------
        self.surf_bloom.fill((0, 0, 0, 0))

        # Massive Grand Stellar Heliosphere & Corona (36 Concentric Steps)
        # Deep space exponential falloff: calm, majestic breathing when idle, expands when speaking
        idle_breathe = 2.5 * math.sin(self.time_elapsed * 0.9)
        max_bloom_r = int(210 + speak_boost * 110 + idle_breathe)
        for step in range(36, 0, -1):
            r_step = int((step / 36.0) * max_bloom_r)
            if r_step >= half_box - 5:
                r_step = half_box - 6
            t = (36 - step) / 36.0  # 0.0 at outer boundary, 1.0 at center
            # Strict high-power exponential falloff: zero at outer perimeter
            alpha_step = int((t ** 3.5) * (46 + speak_boost * 32))
            if alpha_step < 1:
                continue

            c_blend = (
                int(c_prim[0] * (1.0 - t) + c_high[0] * t),
                int(c_prim[1] * (1.0 - t) + c_high[1] * t),
                int(c_prim[2] * (1.0 - t) + c_high[2] * t),
            )
            pygame.draw.circle(self.surf_bloom, (*c_blend, alpha_step), (lx, ly), r_step)

        # Acoustic Shockwave Ripple Rings (Only Active When Speaking)
        if is_speaking or rms > 0.03:
            for wave_i in range(3):
                wave_phase = (self.time_elapsed * 2.2 + wave_i * 0.33) % 1.0
                r_wave = int(35 + wave_phase * (max_bloom_r * 0.90))
                wave_alpha = int(((1.0 - wave_phase) ** 1.5) * (30 + speak_boost * 60))
                if wave_alpha > 0 and r_wave < half_box - 10:
                    pygame.draw.circle(self.surf_bloom, (*c_high, wave_alpha), (lx, ly), r_wave, 2)

        # Concentric Delicate Resonance Rings
        for ring_idx, ring_r in enumerate([int(max_bloom_r * 0.70), int(max_bloom_r * 0.45)]):
            pygame.draw.circle(self.surf_bloom, (*c_high, int(12 + ring_idx * 14 + speak_boost * 18)), (lx, ly), ring_r, 1)

        # Dense Solar Photosphere & White-Gold Singularity Core
        for inner_step in range(16, 0, -1):
            r_in = int((inner_step / 16.0) * (46 + speak_boost * 32))
            t_in = (16 - inner_step) / 16.0
            alpha_in = int((t_in ** 1.8) * (80 + speak_boost * 40) + 8)
            c_in = (
                int(c_high[0] * (1.0 - t_in) + 255 * t_in),
                int(c_high[1] * (1.0 - t_in) + 255 * t_in),
                int(c_high[2] * (1.0 - t_in) + 245 * t_in),
            )
            pygame.draw.circle(self.surf_bloom, (*c_in, min(255, alpha_in)), (lx, ly), r_in)

        self.screen.blit(self.surf_bloom, (box_x, box_y), special_flags=pygame.BLEND_ADD)

        # ----------------------------------------------------------------------
        # 2. 16-Point Deep-Space Astronomical Starburst Diffraction Spikes
        # ----------------------------------------------------------------------
        self.surf_flare.fill((0, 0, 0, 0))
        idle_spike_pulse = 3.0 * math.sin(self.time_elapsed * 1.2)
        base_flare_len = 230 + speak_boost * 180 + idle_spike_pulse

        # A. Primary 4 Cardinal Diamond Needle Spikes
        for i in range(4):
            ang = self.light_rotation + (i * math.pi / 2.0)
            if is_speaking:
                shimmer = 0.84 + 0.16 * math.sin(self.time_elapsed * 8.5 + i * 1.57) + 0.08 * math.sin(self.time_elapsed * 15.2 + i * 2.7)
            else:
                shimmer = 0.94 + 0.06 * math.sin(self.time_elapsed * 3.5 + i * 1.57)

            spike_len = min(half_box - 15, base_flare_len * shimmer)
            waist_w = 4.5 + speak_boost * 4.5
            waist_dist = spike_len * 0.12

            tip = (lx + int(spike_len * math.cos(ang)), ly + int(spike_len * math.sin(ang)))
            perp_ang = ang + math.pi / 2.0
            w_cos = waist_w * math.cos(perp_ang)
            w_sin = waist_w * math.sin(perp_ang)
            waist_cx = lx + int(waist_dist * math.cos(ang))
            waist_cy = ly + int(waist_dist * math.sin(ang))
            p_left = (waist_cx + int(w_cos), waist_cy + int(w_sin))
            p_right = (waist_cx - int(w_cos), waist_cy - int(w_sin))

            pygame.draw.polygon(self.surf_flare, (*c_high, min(255, int(150 + speak_boost * 60))), [(lx, ly), p_left, tip, p_right])

            # Inner Needle Sharp Pure-White Flare
            w_cos_in = (waist_w * 0.3) * math.cos(perp_ang)
            w_sin_in = (waist_w * 0.3) * math.sin(perp_ang)
            p_left_in = (waist_cx + int(w_cos_in), waist_cy + int(w_sin_in))
            p_right_in = (waist_cx - int(w_cos_in), waist_cy - int(w_sin_in))
            pygame.draw.polygon(self.surf_flare, (*c_pure_white, 245), [(lx, ly), p_left_in, tip, p_right_in])

        # B. Secondary 4 Diagonal Diamond Spikes (+45 deg)
        diag_base_len = base_flare_len * 0.65
        for i in range(4):
            ang = self.light_rotation + (math.pi / 4.0) + (i * math.pi / 2.0)
            if is_speaking:
                shimmer = 0.82 + 0.18 * math.cos(self.time_elapsed * 9.5 + i * 2.1)
            else:
                shimmer = 0.94 + 0.06 * math.cos(self.time_elapsed * 3.8 + i * 2.1)

            spike_len = min(half_box - 15, diag_base_len * shimmer)
            waist_w = 3.0 + speak_boost * 3.0
            waist_dist = spike_len * 0.14

            tip = (lx + int(spike_len * math.cos(ang)), ly + int(spike_len * math.sin(ang)))
            perp_ang = ang + math.pi / 2.0
            w_cos = waist_w * math.cos(perp_ang)
            w_sin = waist_w * math.sin(perp_ang)
            waist_cx = lx + int(waist_dist * math.cos(ang))
            waist_cy = ly + int(waist_dist * math.sin(ang))
            p_left = (waist_cx + int(w_cos), waist_cy + int(w_sin))
            p_right = (waist_cx - int(w_cos), waist_cy - int(w_sin))

            pygame.draw.polygon(self.surf_flare, (*c_prim, min(255, int(120 + speak_boost * 50))), [(lx, ly), p_left, tip, p_right])
            pygame.draw.polygon(self.surf_flare, (*c_pure_white, 210), [(lx, ly), p_left, tip, p_right])

        # C. Tertiary 8 Micro-Spikes (+22.5 deg) for 16-point space-telescope look
        tert_base_len = base_flare_len * 0.35
        for i in range(8):
            ang = self.light_rotation + (math.pi / 8.0) + (i * math.pi / 4.0)
            if is_speaking:
                shimmer = 0.75 + 0.25 * math.sin(self.time_elapsed * 11.0 + i * 1.8)
            else:
                shimmer = 0.92 + 0.08 * math.sin(self.time_elapsed * 4.0 + i * 1.8)

            spike_len = min(half_box - 15, tert_base_len * shimmer)
            tip = (lx + int(spike_len * math.cos(ang)), ly + int(spike_len * math.sin(ang)))
            pygame.draw.line(self.surf_flare, (*c_high, int(70 + speak_boost * 45)), (lx, ly), tip, 1)

        # D. Anamorphic Horizontal Lens Flare Streak (Equatorial Prism Beam)
        streak_w = min(half_box - 20, 320 + int(speak_boost * 200))
        streak_h = 3
        streak_pts = [
            (lx - streak_w, ly),
            (lx - int(streak_w * 0.12), ly - streak_h),
            (lx, ly - streak_h - 1),
            (lx + int(streak_w * 0.12), ly - streak_h),
            (lx + streak_w, ly),
            (lx + int(streak_w * 0.12), ly + streak_h),
            (lx, ly + streak_h + 1),
            (lx - int(streak_w * 0.12), ly + streak_h),
        ]
        pygame.draw.polygon(self.surf_flare, (*c_high, min(255, int(135 + speak_boost * 55))), streak_pts)
        pygame.draw.line(self.surf_flare, (*c_pure_white, 240), (lx - streak_w, ly), (lx + streak_w, ly), 2)

        # E. Scintillation Glints (Diamond Sparkle Facets)
        for seed in self.glint_seeds:
            g_ang = seed["angle"] + self.light_rotation * 0.3
            g_dist = seed["dist"] * (0.95 + 0.05 * math.sin(self.time_elapsed * 2.0 + seed["phase"]))
            gx = lx + int(g_dist * math.cos(g_ang))
            gy = ly + int(g_dist * math.sin(g_ang))

            raw_flash = math.sin(self.time_elapsed * seed["freq"] + seed["phase"])
            if raw_flash > 0.15:
                flash_factor = (raw_flash ** 4) * (1.0 + speak_boost * 1.5)
                g_size = seed["size"] * flash_factor
                g_alpha = min(255, int(220 * flash_factor))

                p_top = (gx, gy - int(g_size))
                p_bot = (gx, gy + int(g_size))
                p_left = (gx - int(g_size), gy)
                p_right = (gx + int(g_size), gy)
                pygame.draw.line(self.surf_flare, (*c_pure_white, g_alpha), p_top, p_bot, 2)
                pygame.draw.line(self.surf_flare, (*c_pure_white, g_alpha), p_left, p_right, 2)
                pygame.draw.circle(self.surf_flare, (*c_high, g_alpha), (gx, gy), max(2, int(g_size * 0.35)))

        # F. Orbiting Celestial Photons / Stellar Wind Swarm
        for spk in self.celestial_sparkles:
            spk.update(dt, rms)
            sx, sy = spk.get_pos()
            local_sx = sx - box_x
            local_sy = sy - box_y
            if 0 <= local_sx < box_size and 0 <= local_sy < box_size:
                s_alpha = spk.get_alpha(rms)
                s_size = int(spk.size + (rms * 2.0 if is_speaking else 0.0))
                pygame.draw.circle(self.surf_flare, (*c_high, s_alpha), (local_sx, local_sy), s_size)
                pygame.draw.circle(self.surf_flare, (*c_pure_white, min(255, s_alpha + 40)), (local_sx, local_sy), max(1, s_size // 2))

        self.screen.blit(self.surf_flare, (box_x, box_y), special_flags=pygame.BLEND_ADD)

        # ----------------------------------------------------------------------
        # 3. Ultra-Bright Center Singularity (Intense Photosphere Core)
        # ----------------------------------------------------------------------
        idle_core_pulse = 0.5 * math.sin(self.time_elapsed * 2.0)
        r_singularity = int(9 + speak_boost * 8 + (idle_core_pulse if not is_speaking else 2.5 * math.sin(self.time_elapsed * 8.0)))
        # Inner pure white nucleus
        pygame.draw.circle(self.screen, c_pure_white, (cx, cy), r_singularity)
        # Needle pixel cross at exact focal point
        cross_len = r_singularity + 10
        pygame.draw.line(self.screen, c_pure_white, (cx - cross_len, cy), (cx + cross_len, cy), 2)
        pygame.draw.line(self.screen, c_pure_white, (cx, cy - cross_len), (cx, cy + cross_len), 2)

        # ----------------------------------------------------------------------
        # 4. Symmetrical Crystal FFT Equalizer Bars (Center-Aligned at cy)
        # ----------------------------------------------------------------------
        self.surf_spec.fill((0, 0, 0, 0))
        num_bars = min(len(spectrum), 16 if self.is_vertical else 20)
        bar_w = 5 if self.is_vertical else 6
        bar_gap = 3
        flank_dist = 180 if self.is_vertical else 210
        spec_y_center = cy  # Center-aligned with the star!

        # Left side bars (reversed outwards from cx - flank_dist)
        for i in range(num_bars):
            val = float(spectrum[i])
            bar_h = max(6, int(val * 240 + speak_boost * 60))
            bx_left = (cx - flank_dist) - (i * (bar_w + bar_gap))
            by = spec_y_center - (bar_h // 2)

            bar_alpha = min(255, int(140 + val * 115 + speak_boost * 40))
            bar_color = c_high if val > 0.65 else c_prim
            pygame.draw.rect(
                self.surf_spec,
                (*bar_color, bar_alpha),
                (bx_left, by, bar_w, bar_h),
                border_radius=3,
            )
            pygame.draw.rect(
                self.surf_spec,
                (*c_pure_white, 240),
                (bx_left, by - 3, bar_w, 2),
                border_radius=1,
            )
            pygame.draw.rect(
                self.surf_spec,
                (*c_pure_white, 240),
                (bx_left, by + bar_h + 1, bar_w, 2),
                border_radius=1,
            )

        # Right side bars (outwards from cx + flank_dist)
        for i in range(num_bars):
            val = float(spectrum[i])
            bar_h = max(6, int(val * 240 + speak_boost * 60))
            bx_right = (cx + flank_dist) + (i * (bar_w + bar_gap))
            by = spec_y_center - (bar_h // 2)

            bar_alpha = min(255, int(140 + val * 115 + speak_boost * 40))
            bar_color = c_high if val > 0.65 else c_prim
            pygame.draw.rect(
                self.surf_spec,
                (*bar_color, bar_alpha),
                (bx_right, by, bar_w, bar_h),
                border_radius=3,
            )
            pygame.draw.rect(
                self.surf_spec,
                (*c_pure_white, 240),
                (bx_right, by - 3, bar_w, 2),
                border_radius=1,
            )
            pygame.draw.rect(
                self.surf_spec,
                (*c_pure_white, 240),
                (bx_right, by + bar_h + 1, bar_w, 2),
                border_radius=1,
            )

        self.screen.blit(self.surf_spec, (0, 0))

        # ----------------------------------------------------------------------
        # 5. Lowered Celestial Monogram Badge (Spaced Comfortably Beneath Star)
        # ----------------------------------------------------------------------
        self.surf_emblem.fill((0, 0, 0, 0))
        badge_w, badge_h = 200, 36
        bx, by = cx - badge_w // 2, cy + (180 if self.is_vertical else 200)

        # Glass pill backdrop with audio-reactive border glow
        glow_alpha = min(255, int(160 + speak_boost * 70))
        pygame.draw.rect(self.surf_emblem, (14, 20, 36, 220), (bx, by, badge_w, badge_h), border_radius=18)
        pygame.draw.rect(self.surf_emblem, (*c_high, glow_alpha), (bx, by, badge_w, badge_h), width=1, border_radius=18)

        # Celestial Label
        label_str = f"•  {self.cohost_name.upper()}  •"
        label_rend = self.font_god_badge.render(label_str, True, c_high)
        self.surf_emblem.blit(label_rend, (cx - label_rend.get_width() // 2, by + (badge_h - label_rend.get_height()) // 2))

        self.screen.blit(self.surf_emblem, (0, 0))

    def _draw_top_header(
        self,
        host_connected: bool,
        obs_connected: bool,
        engagement_mode: str = "active",
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
    ):
        """Draws broadcast status bar at top of screen with engagement state and viewer count."""
        self.surf_header.fill((0, 0, 0, 0))
        pygame.draw.rect(self.surf_header, (10, 15, 25, 200), (0, 0, self.width, 60))
        pygame.draw.line(self.surf_header, (50, 70, 110, 150), (0, 59), (self.width, 59), 1)

        # Engagement / Live Status Badge
        mode_lower = engagement_mode.lower()
        if mode_lower == "active" and is_stream_live:
            pulse_alpha = int(180 + 75 * math.sin(self.time_elapsed * 6.0))
            dot_color = (255, 45, 85)
            badge_text = f"LIVE  •  {concurrent_viewers} VIEWERS" if concurrent_viewers > 0 else "LIVE ON AIR"
        elif mode_lower == "eco":
            pulse_alpha = 220
            dot_color = (0, 220, 255)
            badge_text = "ECO (IDLE)"
        else:
            pulse_alpha = 150
            dot_color = (160, 175, 200)
            badge_text = "STANDBY"

        dot_surf = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(dot_surf, (*dot_color, pulse_alpha), (8, 8), 6)
        self.surf_header.blit(dot_surf, (24, 22))

        live_txt = self.font_badge.render(badge_text, True, dot_color)
        self.surf_header.blit(live_txt, (46, 22))

        # Local Host & OBS Status
        host_color = (0, 240, 150) if host_connected else (255, 100, 100)
        host_str = "HOST: LOCAL" if host_connected else "HOST: READY"
        host_txt = self.font_badge.render(host_str, True, host_color)

        # Mood Badge
        c_prim = tuple(int(c) for c in self.c_primary)
        mood_txt = self.font_badge.render(f"MOOD: {self.current_mood.upper()}", True, c_prim)

        if self.is_vertical:
            # Compact 4-column layout for 1080px portrait
            self.surf_header.blit(host_txt, (260, 22))
            self.surf_header.blit(mood_txt, (490, 22))
            ndi_txt = self.font_badge.render("NDI: VERTICAL (9:16)", True, (160, 200, 255))
            self.surf_header.blit(ndi_txt, (self.width - 240, 22))
        else:
            # Full landscape layout for 1920px
            self.surf_header.blit(host_txt, (340, 22))
            obs_color = (0, 240, 150) if obs_connected else (220, 180, 50)
            obs_txt = self.font_badge.render(f"OBS WS: {'ACTIVE' if obs_connected else 'WAITING'}", True, obs_color)
            self.surf_header.blit(obs_txt, (590, 22))
            self.surf_header.blit(mood_txt, (780, 22))
            ndi_txt = self.font_badge.render(f"NDI: {self.cfg.ndi_stream_name} (1080p60)", True, (160, 200, 255))
            self.surf_header.blit(ndi_txt, (self.width - 340, 22))

        self.screen.blit(self.surf_header, (0, 0))

    def _draw_host_transcript_card(self, transcript: str):
        """Draws live host transcript snippet card (Top Right in 16:9, hidden in 9:16)."""
        if self.is_vertical:
            return  # Hidden in vertical 9:16 layout

        card_w, card_h = 560, 140
        card_x, card_y = self.width - card_w - 40, 85

        self.surf_host_card.fill((0, 0, 0, 0))
        # Glassmorphism container
        pygame.draw.rect(self.surf_host_card, (15, 22, 38, 210), (0, 0, card_w, card_h), border_radius=12)
        pygame.draw.rect(self.surf_host_card, (60, 90, 140, 180), (0, 0, card_w, card_h), width=1, border_radius=12)

        # Header tag
        tag_txt = self.font_badge.render("🎙️ HOST / GUEST SPEECH", True, (0, 210, 255))
        self.surf_host_card.blit(tag_txt, (18, 14))

        # Transcript text (wrapped)
        text_to_show = transcript if transcript else "(Listening for host speech...)"
        words = text_to_show.split(" ")
        lines = []
        cur_line = ""
        for w in words:
            test_line = f"{cur_line} {w}".strip()
            if self.font_host_transcript.size(test_line)[0] < card_w - 40:
                cur_line = test_line
            else:
                if cur_line:
                    lines.append(cur_line)
                cur_line = w
        if cur_line:
            lines.append(cur_line)

        # Render top 2-3 lines
        for i, line in enumerate(lines[-3:]):
            txt_rend = self.font_host_transcript.render(line, True, (230, 240, 255))
            self.surf_host_card.blit(txt_rend, (18, 48 + i * 30))

        self.screen.blit(self.surf_host_card, (card_x, card_y))

    def _draw_live_chat_card(self, chat_messages: List[Dict]):
        """
        Draws YouTube Live Chat glassmorphism feed card.
        16:9 Landscape: Left column (w=400, h=640, y=400, up to 7 items).
        9:16 Vertical: Bottom tier below AI Host (w=1000, h=700, y=1140, 3 items).
        """
        if self.is_vertical:
            card_w, card_h = 1000, 700
            card_x, card_y = (self.width - card_w) // 2, 1140
        else:
            card_w, card_h = 400, 640
            card_x, card_y = 40, self.height - card_h - 40

        self.surf_chat_card.fill((0, 0, 0, 0))
        # Main glassmorphism card frame
        pygame.draw.rect(self.surf_chat_card, (12, 18, 32, 220), (0, 0, card_w, card_h), border_radius=14)
        pygame.draw.rect(self.surf_chat_card, (50, 80, 130, 190), (0, 0, card_w, card_h), width=1, border_radius=14)

        # Top Header Strip
        pygame.draw.rect(self.surf_chat_card, (16, 24, 42, 200), (0, 0, card_w, 42), border_top_left_radius=14, border_top_right_radius=14)
        pygame.draw.line(self.surf_chat_card, (60, 90, 140, 150), (0, 42), (card_w, 42), 1)

        tag_txt = self.font_badge.render("💬 LIVE CHAT", True, (255, 195, 60))
        self.surf_chat_card.blit(tag_txt, (18, 12))

        # Live feed indicator dot
        pulse_alpha = int(140 + 115 * math.sin(self.time_elapsed * 6.0))
        dot_surf = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(dot_surf, (0, 240, 150, pulse_alpha), (5, 5), 4)
        self.surf_chat_card.blit(dot_surf, (card_w - 70, 16))
        feed_lbl = self.font_badge.render("FEED", True, (0, 240, 150))
        self.surf_chat_card.blit(feed_lbl, (card_w - 55, 12))

        # Recent messages (3 items in vertical, 7 items in landscape)
        max_msgs = 3 if self.is_vertical else 7
        recent_chats = chat_messages[-max_msgs:] if chat_messages else []
        y_offset = 54
        max_content_y = card_h - 16

        if not recent_chats:
            empty_txt = self.font_chat_msg.render("(Waiting for live chat...)", True, (130, 150, 180))
            self.surf_chat_card.blit(empty_txt, (20, y_offset + 10))
        else:
            for item in recent_chats:
                if y_offset >= max_content_y - 40:
                    break

                is_sc = item.get("is_superchat", False)
                raw_author = item.get("author", "Viewer").strip().lstrip("@")
                clean_author = f"@{raw_author}"
                msg = item.get("message", "").strip()
                amount = item.get("amount", "")

                # Text wrapping
                max_text_w = card_w - 44
                words = msg.split(" ")
                wrapped_lines = []
                cur_l = ""
                for w in words:
                    test_l = f"{cur_l} {w}".strip()
                    if self.font_chat_msg.size(test_l)[0] < max_text_w:
                        cur_l = test_l
                    else:
                        if cur_l:
                            wrapped_lines.append(cur_l)
                        cur_l = w
                if cur_l:
                    wrapped_lines.append(cur_l)

                display_lines = wrapped_lines[:3] if self.is_vertical else (wrapped_lines[:2] if wrapped_lines else [""])
                item_h = 34 + len(display_lines) * 26 + (6 if is_sc else 0)

                # Glass message bubble container
                item_surf = pygame.Surface((card_w - 24, item_h), pygame.SRCALPHA)
                if is_sc:
                    pygame.draw.rect(item_surf, (255, 185, 0, 45), (0, 0, card_w - 24, item_h), border_radius=8)
                    pygame.draw.rect(item_surf, (255, 215, 0, 220), (0, 0, card_w - 24, item_h), width=1, border_radius=8)
                else:
                    pygame.draw.rect(item_surf, (18, 26, 46, 175), (0, 0, card_w - 24, item_h), border_radius=8)
                    pygame.draw.rect(item_surf, (55, 85, 135, 130), (0, 0, card_w - 24, item_h), width=1, border_radius=8)

                author_color = (255, 220, 60) if is_sc else (0, 225, 255)
                sc_badge_str = f" [{amount}]" if is_sc else ""
                auth_rend = self.font_chat_author.render(f"{clean_author}{sc_badge_str}:", True, author_color)
                item_surf.blit(auth_rend, (10, 6))

                msg_color = (255, 250, 240) if is_sc else (235, 242, 255)
                for line_idx, line_text in enumerate(display_lines):
                    line_rend = self.font_chat_msg.render(line_text, True, msg_color)
                    item_surf.blit(line_rend, (10, 30 + line_idx * 26))

                self.surf_chat_card.blit(item_surf, (12, y_offset))
                y_offset += item_h + 12

        self.screen.blit(self.surf_chat_card, (card_x, card_y))

    def _draw_ai_subtitle_card(self, is_speaking: bool):
        """
        Draws AI Co-Host streaming response typewriter banner.
        16:9 Landscape: Bottom-center (w=1000, h=240, y=800).
        9:16 Vertical: Mid tier above chat (w=1000, h=280, y=830).
        """
        if self.is_vertical:
            card_w, card_h = 1000, 280
            card_x, card_y = (self.width - card_w) // 2, 830
        else:
            card_w, card_h = 1000, 240
            card_x, card_y = (self.width - card_w) // 2, self.height - card_h - 40

        self.surf_subtitle_card.fill((0, 0, 0, 0))
        pygame.draw.rect(self.surf_subtitle_card, (15, 20, 36, 230), (0, 0, card_w, card_h), border_radius=14)

        c_prim = tuple(int(c) for c in self.c_primary)
        pygame.draw.rect(self.surf_subtitle_card, (*c_prim, 200), (0, 0, card_w, card_h), width=2, border_radius=14)

        header_title = f"{self.cohost_name.upper()} (HOST)"
        title_rend = self.font_title.render(header_title, True, c_prim)
        self.surf_subtitle_card.blit(title_rend, (24, 16))

        if is_speaking:
            pulse_alpha = int(128 + 127 * math.sin(self.time_elapsed * 8))
            dot_surf = pygame.Surface((14, 14), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (0, 255, 180, pulse_alpha), (7, 7), 6)
            self.surf_subtitle_card.blit(dot_surf, (card_w - 38, 24))
            speaking_lbl = self.font_badge.render("SPEAKING", True, (0, 255, 180))
            self.surf_subtitle_card.blit(speaking_lbl, (card_w - 128, 22))

        # Typewriter text progress
        target_len = len(self.subtitle_target_text)
        if self.typewriter_index < target_len:
            self.typewriter_index = min(target_len, self.typewriter_index + 2)

        text_to_render = self.subtitle_target_text[: self.typewriter_index]
        if not text_to_render:
            host_name = getattr(self.cfg, "host_streamer_name", "Host")
            text_to_render = f"Ready for the next topic! {host_name}, let's keep the energy flowing!"

        words = text_to_render.split(" ")
        lines = []
        cur_line = ""
        max_text_w = card_w - 50
        for w in words:
            test = f"{cur_line} {w}".strip()
            if self.font_ai_subtitle.size(test)[0] < max_text_w:
                cur_line = test
            else:
                if cur_line:
                    lines.append(cur_line)
                cur_line = w
        if cur_line:
            lines.append(cur_line)

        max_lines = 5 if self.is_vertical else 4
        for i, line in enumerate(lines[:max_lines]):
            line_rend = self.font_ai_subtitle.render(line, True, (245, 250, 255))
            self.surf_subtitle_card.blit(line_rend, (24, 64 + i * 36))

        self.screen.blit(self.surf_subtitle_card, (card_x, card_y))

    # --------------------------------------------------------------------------
    # Promotional Callout Graphic Overlays ("Ask God" & "Like & Subscribe")
    # --------------------------------------------------------------------------
    def _update_promo_state(self, dt: float):
        """Updates animation timers and state transitions for promotional callout overlays."""
        transition_duration = 0.6  # Smooth slide & fade transition time in seconds

        if self.promo_state == "off":
            if self.promo_enabled:
                self.promo_timer -= dt
                if self.promo_timer <= 0:
                    self.promo_state = "entrance"
                    self.promo_state_timer = 0.0
                    self.promo_slide_factor = 0.0
                    self.promo_alpha = 0.0
        elif self.promo_state == "entrance":
            self.promo_state_timer += dt
            prog = min(1.0, self.promo_state_timer / transition_duration)
            # Smooth cubic ease-out
            ease = 1.0 - (1.0 - prog) ** 3
            self.promo_slide_factor = ease
            self.promo_alpha = ease
            if prog >= 1.0:
                self.promo_state = "display"
                self.promo_state_timer = 0.0
                self.promo_slide_factor = 1.0
                self.promo_alpha = 1.0
        elif self.promo_state == "display":
            self.promo_state_timer += dt
            self.promo_slide_factor = 1.0
            self.promo_alpha = 1.0
            if self.promo_state_timer >= self.promo_duration:
                self.promo_state = "exit"
                self.promo_state_timer = 0.0
        elif self.promo_state == "exit":
            self.promo_state_timer += dt
            prog = min(1.0, self.promo_state_timer / transition_duration)
            # Smooth cubic ease-in
            ease = prog ** 3
            self.promo_slide_factor = 1.0 - ease
            self.promo_alpha = max(0.0, 1.0 - prog)
            if prog >= 1.0:
                self.promo_state = "off"
                self.promo_state_timer = 0.0
                self.promo_timer = self.promo_interval
                self.promo_slide_factor = 0.0
                self.promo_alpha = 0.0
                # Alternate to the other promo for next appearance
                self.promo_current_type = "like_sub" if self.promo_current_type == "ask_god" else "ask_god"

    def _draw_promo_callout_overlay(self, dt: float):
        """Coordinates and renders the active promotional callout overlay card."""
        self._update_promo_state(dt)

        if self.promo_state == "off" or self.promo_alpha <= 0.005:
            return

        if self.is_vertical:
            card_w, card_h = 760, 146
            target_x = (self.width - card_w) // 2
            target_y = self.core_cy - (card_h // 2)
            start_y = target_y - 40
            cur_x = target_x
            cur_y = int(start_y + (target_y - start_y) * self.promo_slide_factor)
            if self.promo_state == "display":
                cur_y += int(math.sin(self.time_elapsed * 2.8) * 4.0)
        else:
            card_w, card_h = 760, 146
            target_x = 40
            target_y = 95
            start_x = -card_w - 30
            cur_x = int(start_x + (target_x - start_x) * self.promo_slide_factor)
            hover_offset = int(math.sin(self.time_elapsed * 2.8) * 3.0) if self.promo_state == "display" else 0
            cur_y = target_y + hover_offset

        self.surf_promo_card.fill((0, 0, 0, 0))

        if self.promo_current_type == "ask_god":
            self._draw_ask_god_card(self.surf_promo_card, card_w, card_h, self.time_elapsed, self.promo_alpha)
        else:
            self._draw_like_sub_card(self.surf_promo_card, card_w, card_h, self.time_elapsed, self.promo_alpha)

        self.screen.blit(self.surf_promo_card, (cur_x, cur_y))

    def _draw_ask_god_card(self, surf: pygame.Surface, w: int, h: int, t: float, alpha_mult: float):
        """
        Draws the 'Ask God Your Questions Now!' celestial callout card:
        - Deep space sapphire glassmorphic container with radiant gold/cyan border
        - Top centered 'DIVINE Q&A LIVE' badge tag
        - Centered title row with celestial sunbeam question glyph + massive bold title
        - Centered high-legibility subtitle
        - Shimmering specular rim sweep & corner glints
        """
        # 1. Glassmorphism Card Frame
        pygame.draw.rect(surf, (10, 16, 32, min(248, int(245 * alpha_mult))), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(surf, (20, 36, 68, min(180, int(170 * alpha_mult))), (2, 2, w - 4, h - 4), border_radius=14)

        # Radiant Golden/Cyan Border Glow
        border_pulse = 0.85 + 0.15 * math.sin(t * 5.0)
        gold_border = (255, 215, 0)
        pygame.draw.rect(surf, (*gold_border, min(255, int(200 * border_pulse * alpha_mult))), (0, 0, w, h), width=2, border_radius=16)

        # Top rim specular sheen
        pygame.draw.line(surf, (255, 255, 255, min(255, int(160 * alpha_mult))), (24, 2), (w - 24, 2), 1)

        # 2. Top Pill Tag: "DIVINE Q&A LIVE" (Centered)
        tag_txt = self.font_callout_tag.render("DIVINE Q&A LIVE", True, (0, 240, 255))
        tag_w = tag_txt.get_width() + 34
        tag_h = 22
        tag_x = (w - tag_w) // 2
        tag_y = 12

        pygame.draw.rect(surf, (0, 200, 255, min(255, int(50 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), border_radius=11)
        pygame.draw.rect(surf, (0, 240, 255, min(255, int(180 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), width=1, border_radius=11)

        # Pulsating Live Cyan Dot
        dot_a = min(255, int((160 + 95 * math.sin(t * 6.0)) * alpha_mult))
        pygame.draw.circle(surf, (0, 255, 200, dot_a), (tag_x + 12, tag_y + tag_h // 2), 4)
        surf.blit(tag_txt, (tag_x + 22, tag_y + 2))

        # 3. Middle Title Row: Celestial Question Badge + Title (Centered Lockup)
        title_str = "Ask God Your Questions Now!"
        title_rend = self.font_callout_title.render(title_str, True, (255, 250, 230))
        sh_rend = self.font_callout_title.render(title_str, True, (180, 140, 20))

        badge_r = 17
        lockup_gap = 14
        total_title_w = (badge_r * 2 + 8) + lockup_gap + title_rend.get_width()
        lockup_x = (w - total_title_w) // 2
        badge_cx = lockup_x + badge_r + 4
        badge_cy = 58
        title_x = lockup_x + (badge_r * 2 + 8) + lockup_gap
        title_y = 41

        # Rotating halo rays around question badge
        ray_angle_base = t * 1.6
        for i in range(8):
            ang = ray_angle_base + i * (math.pi / 4.0)
            r_in = badge_r + 2
            r_out = badge_r + 7 + 3.0 * math.sin(t * 6.0 + i)
            p1 = (int(badge_cx + r_in * math.cos(ang)), int(badge_cy + r_in * math.sin(ang)))
            p2 = (int(badge_cx + r_out * math.cos(ang)), int(badge_cy + r_out * math.sin(ang)))
            pygame.draw.line(surf, (255, 215, 0, min(255, int(170 * alpha_mult))), p1, p2, 2)

        # Core Badge Circle
        pygame.draw.circle(surf, (20, 36, 68, min(255, int(240 * alpha_mult))), (badge_cx, badge_cy), badge_r)
        pygame.draw.circle(surf, (255, 215, 0, min(255, int(230 * alpha_mult))), (badge_cx, badge_cy), badge_r, 2)
        pygame.draw.circle(surf, (0, 240, 255, min(255, int(130 * alpha_mult))), (badge_cx, badge_cy), badge_r - 4, 1)

        # White Question Mark Glyph
        q_rend = self.font_callout_icon.render("?", True, (255, 255, 255))
        surf.blit(q_rend, (badge_cx - q_rend.get_width() // 2, badge_cy - q_rend.get_height() // 2 - 1))

        # Title Blit with shadow
        surf.blit(sh_rend, (title_x + 2, title_y + 2))
        surf.blit(title_rend, (title_x, title_y))

        # 4. Bottom Subtitle Row (Centered)
        sub_str = "Drop your questions in chat • Divine wisdom & roasts!"
        sub_rend = self.font_callout_sub.render(sub_str, True, (195, 225, 255))
        sub_x = (w - sub_rend.get_width()) // 2
        sub_y = 96
        surf.blit(sub_rend, (sub_x, sub_y))

        # 5. Specular Rim Sheen Light Sweep
        shimmer_pos = int((t * 280) % (w + 140)) - 70
        if 0 <= shimmer_pos < w:
            s_left = max(10, shimmer_pos - 35)
            s_right = min(w - 10, shimmer_pos + 35)
            pygame.draw.line(surf, (255, 255, 255, min(255, int(220 * alpha_mult))), (s_left, 1), (s_right, 1), 2)
            pygame.draw.line(surf, (255, 215, 0, min(255, int(180 * alpha_mult))), (s_left, h - 2), (s_right, h - 2), 2)

        # 6. Corner Sparkle Glints
        sp_a = min(255, int((140 + 115 * math.sin(t * 8.0)) * alpha_mult))
        for sp_pos in [(w - 18, 18), (w - 28, h - 18)]:
            sx, sy = sp_pos
            pygame.draw.circle(surf, (255, 255, 255, sp_a), (sx, sy), 2)
            pygame.draw.line(surf, (255, 215, 0, sp_a), (sx - 6, sy), (sx + 6, sy), 1)
            pygame.draw.line(surf, (255, 215, 0, sp_a), (sx, sy - 6), (sx, sy + 6), 1)

    def _draw_like_sub_card(self, surf: pygame.Surface, w: int, h: int, t: float, alpha_mult: float):
        """
        Draws the 'Like & Subscribe!' creator community callout card:
        - Sleek ruby-tinted glassmorphic container with neon coral/magenta border
        - Top centered 'COMMUNITY HYPE' badge tag
        - Centered title row with YouTube Play badge + ringing bell + massive bold title
        - Centered high-legibility subtitle
        - Shimmering specular rim sweep & corner glints
        """
        # 1. Glassmorphism Card Frame
        pygame.draw.rect(surf, (24, 10, 20, min(248, int(245 * alpha_mult))), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(surf, (48, 16, 34, min(180, int(170 * alpha_mult))), (2, 2, w - 4, h - 4), border_radius=14)

        # Radiant Neon Coral/Ruby Border Glow
        border_pulse = 0.85 + 0.15 * math.sin(t * 5.0)
        coral_border = (255, 50, 90)
        pygame.draw.rect(surf, (*coral_border, min(255, int(200 * border_pulse * alpha_mult))), (0, 0, w, h), width=2, border_radius=16)

        # Top rim specular sheen
        pygame.draw.line(surf, (255, 220, 230, min(255, int(160 * alpha_mult))), (24, 2), (w - 24, 2), 1)

        # 2. Top Pill Tag: "COMMUNITY HYPE" (Centered)
        tag_txt = self.font_callout_tag.render("COMMUNITY HYPE", True, (255, 100, 130))
        tag_w = tag_txt.get_width() + 34
        tag_h = 22
        tag_x = (w - tag_w) // 2
        tag_y = 12

        pygame.draw.rect(surf, (255, 40, 80, min(255, int(50 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), border_radius=11)
        pygame.draw.rect(surf, (255, 60, 100, min(255, int(180 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), width=1, border_radius=11)

        # Pulsating Live Red Dot
        dot_a = min(255, int((160 + 95 * math.sin(t * 6.0)) * alpha_mult))
        pygame.draw.circle(surf, (255, 50, 90, dot_a), (tag_x + 12, tag_y + tag_h // 2), 4)
        surf.blit(tag_txt, (tag_x + 22, tag_y + 2))

        # 3. Middle Title Row: YouTube & Bell Badge + Title (Centered Lockup)
        title_str = "Like & Subscribe!"
        title_rend = self.font_callout_title.render(title_str, True, (255, 245, 245))
        sh_rend = self.font_callout_title.render(title_str, True, (160, 20, 50))

        pill_w, pill_h = 44, 28
        badge_area_w = pill_w + 14
        lockup_gap = 14
        total_title_w = badge_area_w + lockup_gap + title_rend.get_width()
        lockup_x = (w - total_title_w) // 2

        # YouTube Red Squircle Pill
        pill_x = lockup_x
        pill_y = 44
        pygame.draw.rect(surf, (255, 20, 50, min(255, int(240 * alpha_mult))), (pill_x, pill_y, pill_w, pill_h), border_radius=8)
        pygame.draw.rect(surf, (255, 255, 255, min(255, int(180 * alpha_mult))), (pill_x, pill_y, pill_w, pill_h), width=1, border_radius=8)

        # White play triangle inside pill
        tri_pts = [
            (pill_x + 16, pill_y + 7),
            (pill_x + 16, pill_y + 21),
            (pill_x + 30, pill_y + 14),
        ]
        pygame.draw.polygon(surf, (255, 255, 255, min(255, int(250 * alpha_mult))), tri_pts)

        # Ringing Golden Notification Bell badge overlapping lower right
        bell_cx = pill_x + pill_w - 2
        bell_cy = pill_y + pill_h - 2
        swing = math.sin(t * 8.0)
        clapper_x = int(bell_cx + swing * 3.5)

        # Bell pill background
        pygame.draw.circle(surf, (35, 15, 25, min(255, int(240 * alpha_mult))), (bell_cx, bell_cy), 13)
        pygame.draw.circle(surf, (255, 200, 50, min(255, int(220 * alpha_mult))), (bell_cx, bell_cy), 13, 1)

        # Bell Dome
        bell_pts = [
            (bell_cx - 6, bell_cy + 3),
            (bell_cx - 3, bell_cy - 5),
            (bell_cx + 3, bell_cy - 5),
            (bell_cx + 6, bell_cy + 3),
        ]
        pygame.draw.polygon(surf, (255, 215, 0, min(255, int(245 * alpha_mult))), bell_pts)
        pygame.draw.circle(surf, (255, 240, 120, min(255, int(250 * alpha_mult))), (clapper_x, bell_cy + 5), 3)

        # Sound arcs around ringing bell
        if abs(swing) > 0.35:
            arc_a = min(255, int(abs(swing) * 210 * alpha_mult))
            pygame.draw.arc(surf, (255, 200, 50, arc_a), (bell_cx - 12, bell_cy - 6, 7, 11), math.pi * 0.6, math.pi * 1.4, 2)
            pygame.draw.arc(surf, (255, 200, 50, arc_a), (bell_cx + 5, bell_cy - 6, 7, 11), -math.pi * 0.4, math.pi * 0.4, 2)

        # Title Blit
        title_x = lockup_x + badge_area_w + lockup_gap
        title_y = 41
        surf.blit(sh_rend, (title_x + 2, title_y + 2))
        surf.blit(title_rend, (title_x, title_y))

        # 4. Bottom Subtitle Row (Centered)
        sub_str = "Smash like & ring bell for live stream alerts!"
        sub_rend = self.font_callout_sub.render(sub_str, True, (255, 220, 205))
        sub_x = (w - sub_rend.get_width()) // 2
        sub_y = 96
        surf.blit(sub_rend, (sub_x, sub_y))

        # 5. Specular Rim Sheen Light Sweep
        shimmer_pos = int((t * 280) % (w + 140)) - 70
        if 0 <= shimmer_pos < w:
            s_left = max(10, shimmer_pos - 35)
            s_right = min(w - 10, shimmer_pos + 35)
            pygame.draw.line(surf, (255, 255, 255, min(255, int(220 * alpha_mult))), (s_left, 1), (s_right, 1), 2)
            pygame.draw.line(surf, (255, 60, 120, min(255, int(180 * alpha_mult))), (s_left, h - 2), (s_right, h - 2), 2)

        # 6. Corner Sparkle Glints
        sp_a = min(255, int((140 + 115 * math.sin(t * 8.0)) * alpha_mult))
        for sp_pos in [(w - 18, 18), (w - 28, h - 18)]:
            sx, sy = sp_pos
            pygame.draw.circle(surf, (255, 255, 255, sp_a), (sx, sy), 2)
            pygame.draw.line(surf, (255, 60, 120, sp_a), (sx - 6, sy), (sx + 6, sy), 1)
            pygame.draw.line(surf, (255, 60, 120, sp_a), (sx, sy - 6), (sx, sy + 6), 1)

    def close(self):
        """Closes Pygame display window and releases SDL hardware surfaces."""
        try:
            pygame.display.quit()
            pygame.quit()
        except Exception:
            pass


