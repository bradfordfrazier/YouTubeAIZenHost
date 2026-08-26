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

        # Enable Windows Per-Monitor DPI Awareness so the desktop window matches physical pixels
        # without Windows DWM scaling/blurring it past monitor boundaries
        if os.name == "nt":
            try:
                import ctypes
                try:
                    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
                except Exception:
                    try:
                        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
                    except Exception:
                        ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        # Center desktop window on monitor
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")

        pygame.init()
        pygame.font.init()

        self.should_quit = False
        if self.cfg.visualizer_headless:
            self.window_surf = None
            self.screen = pygame.Surface((self.width, self.height))
            self.window_size = (self.width, self.height)
        else:
            if getattr(self.cfg, "visualizer_native_window", False):
                win_w = window_width or self.width
                win_h = window_height or self.height
            else:
                default_win_w = 540 if self.is_vertical else 640
                default_win_h = 960 if self.is_vertical else 360
                cfg_w = getattr(self.cfg, "visualizer_window_width", None)
                cfg_h = getattr(self.cfg, "visualizer_window_height", None)
                if cfg_w and cfg_h and ((cfg_h > cfg_w) == self.is_vertical):
                    win_w = window_width or cfg_w
                    win_h = window_height or cfg_h
                else:
                    win_w = window_width or default_win_w
                    win_h = window_height or default_win_h
            self.window_size = (win_w, win_h)
            flags = pygame.DOUBLEBUF | pygame.RESIZABLE
            if getattr(self.cfg, "visualizer_borderless", False):
                flags = pygame.DOUBLEBUF | pygame.NOFRAME
            self.window_surf = pygame.display.set_mode(self.window_size, flags)
            pygame.event.set_grab(False)
            pygame.mouse.set_visible(True)
            caption_mode = "Vertical 9:16 (1080x1920)" if self.is_vertical else "Landscape 16:9 (1920x1080)"
            pygame.display.set_caption(f"AI Co-Host Broadcast Visualizer - {caption_mode}")
            # Internal full-resolution rendering surface (always full 1080x1920 or 1920x1080 for NDI)
            self.screen = pygame.Surface((self.width, self.height))

        self.clock = pygame.time.Clock()

        # Resolution-Aware High-Legibility Typography
        # In 9:16 vertical mode (1080x1920), font sizes are scaled up to broadcast/mobile standards
        # so text remains crisp, prominent, and readable in OBS dock previews and on mobile devices.
        if self.is_vertical:
            self.font_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 34, bold=True)
            self.font_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 24)
            self.font_ai_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 36, bold=True)
            self.font_host_transcript = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 24)
            self.font_small = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 18)
            self.font_badge = pygame.font.SysFont("Consolas, Segoe UI, sans-serif", 22, bold=True)
            self.font_chat_author = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 28, bold=True)
            self.font_chat_msg = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 26)
            self.font_god_badge = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 26, bold=True)
            self.font_callout_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 38, bold=True)
            self.font_callout_sub = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 24, bold=True)
            self.font_callout_tag = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 20, bold=True)
            self.font_callout_icon = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 34, bold=True)
        else:
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

        # Ambient Particle System (optimally tuned for 60+ FPS on Intel Core i5 / UHD 630 Graphics)
        self.num_particles = getattr(self.cfg, "visualizer_particle_count", 70)
        self.particles = [Particle(self.width, self.height) for _ in range(self.num_particles)]

        # Celestial Sparkle System around the central Point of Light
        self.core_cx = self.width // 2
        self.core_cy = 440 if self.is_vertical else 430
        self.num_sparkles = 25
        self.celestial_sparkles = [
            CelestialSparkle(self.core_cx, self.core_cy) for _ in range(self.num_sparkles)
        ]

        # Celebration Fireworks & Confetti Burst System
        self.celebration_particles: List[CelebrationParticle] = []
        self.celebration_timer: float = 0.0

        # Promotional Callout Overlays ("Ask Me Your Questions", "Like & Subscribe")
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

        # Pre-render high-resolution multi-layer radial corona / bloom sprites for all moods
        # Replaces CPU-heavy per-frame concentric circle rasterization with instant GPU/CPU blits
        self._bloom_sprites = {}
        sprite_sz = 256
        half_sz = sprite_sz // 2
        for mood_key, p_val in ColorPalette.PALETTES.items():
            spr = pygame.Surface((sprite_sz, sprite_sz), pygame.SRCALPHA)
            c_p = p_val["primary"]
            c_h = p_val["highlight"]
            for r in range(half_sz, 0, -2):
                t = (half_sz - r) / half_sz  # 0.0 at outer edge, 1.0 at center
                alpha = int((t ** 3.0) * 230)
                if alpha < 2:
                    continue
                col = (
                    int(c_p[0] * (1.0 - t) + c_h[0] * t),
                    int(c_p[1] * (1.0 - t) + c_h[1] * t),
                    int(c_p[2] * (1.0 - t) + c_h[2] * t),
                    alpha,
                )
                pygame.draw.circle(spr, col, (half_sz, half_sz), r)
            self._bloom_sprites[mood_key] = spr

        # Tightly-bounded scratch surfaces for maximum memory bandwidth efficiency on UHD Graphics
        self.box_size = 560
        self.surf_flare = pygame.Surface((self.box_size, self.box_size), pygame.SRCALPHA)

        # Adaptive card dimensions
        host_w, host_h = (1000, 140) if self.is_vertical else (560, 140)
        chat_w, chat_h = (1000, 700) if self.is_vertical else (400, 640)
        sub_w, sub_h = (1000, 328) if self.is_vertical else (1000, 276)
        promo_w, promo_h = (860, 175) if self.is_vertical else (760, 146)

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
                    flags = pygame.DOUBLEBUF | pygame.RESIZABLE
                    if getattr(self.cfg, "visualizer_borderless", False):
                        flags = pygame.DOUBLEBUF | pygame.NOFRAME
                    self.window_surf = pygame.display.set_mode(self.window_size, flags)
                    pygame.event.set_grab(False)
                    pygame.mouse.set_visible(True)
                elif event.type == pygame.QUIT:
                    self.should_quit = True

            # Scale the high-res render canvas to the desktop window container
            if self.window_size == (self.width, self.height):
                self.window_surf.blit(self.screen, (0, 0))
            else:
                pygame.transform.smoothscale(self.screen, self.window_size, self.window_surf)
            pygame.display.flip()

        # Return full pristine RGBA buffer for NDI (always 1080x1920 or 1920x1080)
        return pygame.image.tobytes(self.screen, "RGBA")

    def _draw_celebration_fx(self, dt: float):
        """Draws radiant fireworks and celestial confetti particles directly onto the canvas."""
        if self.celebration_timer > 0:
            self.celebration_timer = max(0.0, self.celebration_timer - dt)
            # Continually spawn sparkle fountains while celebration timer is active
            if random.random() < 0.35:
                for _ in range(4):
                    self.celebration_particles.append(CelebrationParticle(self.core_cx, self.core_cy))

        if not self.celebration_particles:
            return

        alive_particles = []
        for p in self.celebration_particles:
            p.update()
            if p.is_alive and p.alpha > 5:
                alive_particles.append(p)
                col = p.color
                ix, iy = int(p.x), int(p.y)
                sz = max(2, int(p.size))

                if p.shape == "circle":
                    pygame.draw.circle(self.screen, col, (ix, iy), sz)
                elif p.shape == "diamond":
                    pts = [
                        (ix, iy - sz),
                        (ix + sz, iy),
                        (ix, iy + sz),
                        (ix - sz, iy),
                    ]
                    pygame.draw.polygon(self.screen, col, pts)
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
                    pygame.draw.polygon(self.screen, col, pts)

        self.celebration_particles = alive_particles

    # --------------------------------------------------------------------------
    # Drawing Components
    # --------------------------------------------------------------------------
    def _draw_dynamic_background(self, rms: float):
        """Draws fluid dynamic gradient backdrop and subtle undulating energy waves."""
        c_top = tuple(int(c) for c in self.c_bg_dark)
        c_bot = tuple(int(c) for c in self.c_bg_accent)

        # Base background fill
        self.screen.fill(c_top)

        # Ambient radial glow drawn into localized bloom surface for maximum FPS
        center_x, center_y = self.core_cx, self.core_cy
        glow_r = int(220 + rms * 160)
        c_prim = tuple(int(c) for c in self.c_primary)
        glow_box = glow_r * 2
        if not hasattr(self, "_surf_ambient_glow") or self._surf_ambient_glow.get_width() != glow_box:
            self._surf_ambient_glow = pygame.Surface((glow_box, glow_box), pygame.SRCALPHA)
        self._surf_ambient_glow.fill((0, 0, 0, 0))
        pygame.draw.circle(
            self._surf_ambient_glow,
            (*c_prim, int(25 + rms * 40)),
            (glow_r, glow_r),
            glow_r,
        )
        self.screen.blit(self._surf_ambient_glow, (center_x - glow_r, center_y - glow_r), special_flags=pygame.BLEND_ADD)

        # Flowing sine wave ribbons in lower half (drawn directly on canvas)
        c_sec = tuple(int(c) for c in self.c_secondary)
        num_waves = 3
        base_y_start = 1450 if self.is_vertical else 650
        y_step = 80 if self.is_vertical else 60
        for w_idx in range(num_waves):
            pts = []
            freq = 0.003 + w_idx * 0.0015
            phase = self.time_elapsed * (1.2 + w_idx * 0.4)
            amp = 25.0 + w_idx * 15.0 + rms * 60.0
            base_y = base_y_start + w_idx * y_step

            for x in range(0, self.width + 40, 30):
                y = base_y + math.sin(x * freq + phase) * amp + math.cos(x * 0.001 - phase * 0.5) * 15
                pts.append((x, int(y)))

            if len(pts) > 1:
                pygame.draw.lines(self.screen, c_sec, False, pts, 2)

    def _draw_particles(self, speed_mult: float, rms: float):
        """Update and draw ambient floating particles directly."""
        c_high = tuple(int(c) for c in self.c_highlight)

        for p in self.particles:
            p.update(speed_mult, rms)
            alpha_col = c_high if p.alpha > 180 else tuple(int(c * 0.75) for c in c_high)
            pygame.draw.circle(self.screen, alpha_col, (int(p.x), int(p.y)), int(p.size))

    def _draw_hologram_core(self, rms: float, spectrum: np.ndarray, is_speaking: bool):
        """
        Draws the central massive star shining in the distance:
        - Instant pre-rendered celestial corona sprite blit (0.1ms GPU/CPU)
        - Audio-reactive acoustic shockwave ripple rings when speaking
        - 16-point space-telescope astronomical starburst diffraction spikes
        - Slender anamorphic horizontal equator flare streak
        - Orbiting celestial sparkle photons & scintillation glints
        - Pure white-hot solar photosphere & singularity nucleus
        - Center-aligned symmetrical crystal equalizer bars flanking the star
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

        # ----------------------------------------------------------------------
        # 1. Pre-Rendered High-Speed Stellar Corona & Atmospheric Glow
        # ----------------------------------------------------------------------
        bloom_spr = self._bloom_sprites.get(self.current_mood, list(self._bloom_sprites.values())[0])
        idle_breathe = 2.5 * math.sin(self.time_elapsed * 0.9)
        max_bloom_r = int(190 + speak_boost * 95 + idle_breathe)
        spr_dim = max_bloom_r * 2
        scaled_bloom = pygame.transform.scale(bloom_spr, (spr_dim, spr_dim))
        self.screen.blit(scaled_bloom, (cx - max_bloom_r, cy - max_bloom_r), special_flags=pygame.BLEND_ADD)

        # Acoustic Shockwave Ripple Rings (Active When Speaking)
        if is_speaking or rms > 0.03:
            for wave_i in range(2):
                wave_phase = (self.time_elapsed * 2.2 + wave_i * 0.5) % 1.0
                r_wave = int(35 + wave_phase * (max_bloom_r * 0.90))
                pygame.draw.circle(self.screen, c_high, (cx, cy), r_wave, 2)

        # ----------------------------------------------------------------------
        # 2. 16-Point Deep-Space Starburst Diffraction Spikes & Scintillation
        # ----------------------------------------------------------------------
        self.surf_flare.fill((0, 0, 0, 0))
        half_box = self.box_size // 2
        box_x = cx - half_box
        box_y = cy - half_box
        lx, ly = half_box, half_box

        idle_spike_pulse = 3.0 * math.sin(self.time_elapsed * 1.2)
        base_flare_len = min(half_box - 15, 200 + speak_boost * 140 + idle_spike_pulse)

        # A. Primary 4 Cardinal Diamond Needle Spikes
        for i in range(4):
            ang = self.light_rotation + (i * math.pi / 2.0)
            shimmer = (0.84 + 0.16 * math.sin(self.time_elapsed * 8.5 + i * 1.57)) if is_speaking else (0.94 + 0.06 * math.sin(self.time_elapsed * 3.5 + i * 1.57))
            spike_len = min(half_box - 15, base_flare_len * shimmer)
            waist_w = 4.0 + speak_boost * 3.5
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
            shimmer = (0.82 + 0.18 * math.cos(self.time_elapsed * 9.5 + i * 2.1)) if is_speaking else (0.94 + 0.06 * math.cos(self.time_elapsed * 3.8 + i * 2.1))
            spike_len = min(half_box - 15, diag_base_len * shimmer)
            waist_w = 2.5 + speak_boost * 2.5
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

        # C. Tertiary 8 Micro-Spikes (+22.5 deg)
        tert_base_len = base_flare_len * 0.35
        for i in range(8):
            ang = self.light_rotation + (math.pi / 8.0) + (i * math.pi / 4.0)
            shimmer = (0.75 + 0.25 * math.sin(self.time_elapsed * 11.0 + i * 1.8)) if is_speaking else 1.0
            spike_len = min(half_box - 15, tert_base_len * shimmer)
            tip = (lx + int(spike_len * math.cos(ang)), ly + int(spike_len * math.sin(ang)))
            pygame.draw.line(self.surf_flare, (*c_high, int(70 + speak_boost * 45)), (lx, ly), tip, 1)

        # D. Anamorphic Horizontal Lens Flare Streak (Equatorial Beam)
        streak_w = min(half_box - 20, 260 + int(speak_boost * 150))
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
            if 0 <= local_sx < self.box_size and 0 <= local_sy < self.box_size:
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
        pygame.draw.circle(self.screen, c_pure_white, (cx, cy), r_singularity)
        cross_len = r_singularity + 10
        pygame.draw.line(self.screen, c_pure_white, (cx - cross_len, cy), (cx + cross_len, cy), 2)
        pygame.draw.line(self.screen, c_pure_white, (cx, cy - cross_len), (cx, cy + cross_len), 2)

        # ----------------------------------------------------------------------
        # 4. Symmetrical Crystal FFT Equalizer Bars (Direct on canvas)
        # ----------------------------------------------------------------------
        num_bars = min(len(spectrum), 16 if self.is_vertical else 20)
        bar_w = 5 if self.is_vertical else 6
        bar_gap = 3
        flank_dist = 180 if self.is_vertical else 210
        spec_y_center = cy

        # Left side bars
        for i in range(num_bars):
            val = float(spectrum[i])
            bar_h = max(6, int(val * 240 + speak_boost * 60))
            bx_left = (cx - flank_dist) - (i * (bar_w + bar_gap))
            by = spec_y_center - (bar_h // 2)
            bar_color = c_high if val > 0.65 else c_prim
            pygame.draw.rect(self.screen, bar_color, (bx_left, by, bar_w, bar_h), border_radius=3)
            pygame.draw.rect(self.screen, c_pure_white, (bx_left, by - 3, bar_w, 2), border_radius=1)
            pygame.draw.rect(self.screen, c_pure_white, (bx_left, by + bar_h + 1, bar_w, 2), border_radius=1)

        # Right side bars
        for i in range(num_bars):
            val = float(spectrum[i])
            bar_h = max(6, int(val * 240 + speak_boost * 60))
            bx_right = (cx + flank_dist) + (i * (bar_w + bar_gap))
            by = spec_y_center - (bar_h // 2)
            bar_color = c_high if val > 0.65 else c_prim
            pygame.draw.rect(self.screen, bar_color, (bx_right, by, bar_w, bar_h), border_radius=3)
            pygame.draw.rect(self.screen, c_pure_white, (bx_right, by - 3, bar_w, 2), border_radius=1)
            pygame.draw.rect(self.screen, c_pure_white, (bx_right, by + bar_h + 1, bar_w, 2), border_radius=1)

        # ----------------------------------------------------------------------
        # 5. Lowered Celestial Monogram Badge (Direct on canvas)
        # ----------------------------------------------------------------------
        badge_w, badge_h = (220, 48) if self.is_vertical else (200, 36)
        bx, by = cx - badge_w // 2, cy + (275 if self.is_vertical else 265)

        pygame.draw.rect(self.screen, (14, 20, 36), (bx, by, badge_w, badge_h), border_radius=badge_h // 2)
        pygame.draw.rect(self.screen, c_high, (bx, by, badge_w, badge_h), width=1, border_radius=badge_h // 2)

        label_str = f"•  {self.cohost_name.upper()}  •"
        label_rend = self.font_god_badge.render(label_str, True, c_high)
        self.screen.blit(label_rend, (cx - label_rend.get_width() // 2, by + (badge_h - label_rend.get_height()) // 2))

    def _draw_top_header(
        self,
        host_connected: bool,
        obs_connected: bool,
        engagement_mode: str = "active",
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
    ):
        """Draws broadcast status bar at top of screen directly on canvas."""
        bar_h = 70 if self.is_vertical else 60
        txt_y = 20 if self.is_vertical else 22
        dot_y = 35 if self.is_vertical else 30
        dot_r = 7 if self.is_vertical else 6

        pygame.draw.rect(self.screen, (10, 15, 25), (0, 0, self.width, bar_h))
        pygame.draw.line(self.screen, (50, 70, 110), (0, bar_h - 1), (self.width, bar_h - 1), 1)

        # Engagement / Live Status Badge
        mode_lower = engagement_mode.lower()
        if mode_lower == "active" and is_stream_live:
            dot_color = (255, 45, 85)
            badge_text = f"LIVE  •  {concurrent_viewers} VIEWERS" if concurrent_viewers > 0 else "LIVE ON AIR"
        elif mode_lower == "eco":
            dot_color = (0, 220, 255)
            badge_text = "ECO (IDLE)"
        else:
            dot_color = (160, 175, 200)
            badge_text = "STANDBY"

        pygame.draw.circle(self.screen, dot_color, (30, dot_y), dot_r)
        live_txt = self.font_badge.render(badge_text, True, dot_color)
        self.screen.blit(live_txt, (48, txt_y))

        # Local Host & OBS Status
        host_color = (0, 240, 150) if host_connected else (255, 100, 100)
        host_str = "HOST: LOCAL" if host_connected else "HOST: READY"
        host_txt = self.font_badge.render(host_str, True, host_color)

        # Mood Badge
        c_prim = tuple(int(c) for c in self.c_primary)
        mood_txt = self.font_badge.render(f"MOOD: {self.current_mood.upper()}", True, c_prim)

        if self.is_vertical:
            self.screen.blit(host_txt, (320, txt_y))
            self.screen.blit(mood_txt, (540, txt_y))
            ndi_txt = self.font_badge.render("NDI: 9:16", True, (160, 200, 255))
            self.screen.blit(ndi_txt, (self.width - ndi_txt.get_width() - 30, txt_y))
        else:
            self.screen.blit(host_txt, (340, txt_y))
            obs_color = (0, 240, 150) if obs_connected else (220, 180, 50)
            obs_txt = self.font_badge.render(f"OBS WS: {'ACTIVE' if obs_connected else 'WAITING'}", True, obs_color)
            self.screen.blit(obs_txt, (590, txt_y))
            self.screen.blit(mood_txt, (780, txt_y))
            ndi_txt = self.font_badge.render(f"NDI: {self.cfg.ndi_stream_name} (1080p60)", True, (160, 200, 255))
            self.screen.blit(ndi_txt, (self.width - 340, txt_y))

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
        9:16 Vertical: Bottom tier below AI Host (w=1000, h=700, y=1140, up to 5 items).
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
        strip_h = 52 if self.is_vertical else 42
        pygame.draw.rect(self.surf_chat_card, (16, 24, 42, 200), (0, 0, card_w, strip_h), border_top_left_radius=14, border_top_right_radius=14)
        pygame.draw.line(self.surf_chat_card, (60, 90, 140, 150), (0, strip_h), (card_w, strip_h), 1)

        tag_txt = self.font_badge.render("💬 LIVE CHAT", True, (255, 195, 60))
        tag_y = 14 if self.is_vertical else 12
        self.surf_chat_card.blit(tag_txt, (20 if self.is_vertical else 18, tag_y))

        # Live feed indicator dot
        pulse_alpha = int(140 + 115 * math.sin(self.time_elapsed * 6.0))
        dot_surf = pygame.Surface((12, 12), pygame.SRCALPHA)
        pygame.draw.circle(dot_surf, (0, 240, 150, pulse_alpha), (6, 6), 5)
        feed_lbl = self.font_badge.render("FEED", True, (0, 240, 150))
        feed_lbl_w = feed_lbl.get_width()
        dot_x = card_w - feed_lbl_w - 40
        feed_x = card_w - feed_lbl_w - 20
        self.surf_chat_card.blit(dot_surf, (dot_x, tag_y + 4))
        self.surf_chat_card.blit(feed_lbl, (feed_x, tag_y))

        # Recent messages (5 items in vertical, 7 items in landscape)
        max_msgs = 5 if self.is_vertical else 7
        recent_chats = chat_messages[-max_msgs:] if chat_messages else []
        y_offset = 66 if self.is_vertical else 54
        max_content_y = card_h - 16

        if not recent_chats:
            empty_txt = self.font_chat_msg.render("(Waiting for live chat...)", True, (130, 150, 180))
            self.surf_chat_card.blit(empty_txt, (20, y_offset + 10))
        else:
            for item in recent_chats:
                is_sc = item.get("is_superchat", False)
                raw_author = item.get("author", "Viewer").strip().lstrip("@")
                clean_author = f"@{raw_author}"
                msg = item.get("message", "").strip()
                amount = item.get("amount", "")

                # Text wrapping
                max_text_w = card_w - (56 if self.is_vertical else 44)
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

                display_lines = wrapped_lines[:2] if self.is_vertical else (wrapped_lines[:2] if wrapped_lines else [""])
                line_h = 34 if self.is_vertical else 26
                auth_h = 38 if self.is_vertical else 28
                item_h = auth_h + len(display_lines) * line_h + (8 if is_sc else 4)

                if y_offset + item_h > max_content_y:
                    break

                # Glass message bubble container
                item_surf = pygame.Surface((card_w - 24, item_h), pygame.SRCALPHA)
                if is_sc:
                    pygame.draw.rect(item_surf, (255, 185, 0, 45), (0, 0, card_w - 24, item_h), border_radius=10)
                    pygame.draw.rect(item_surf, (255, 215, 0, 220), (0, 0, card_w - 24, item_h), width=1, border_radius=10)
                else:
                    pygame.draw.rect(item_surf, (18, 26, 46, 175), (0, 0, card_w - 24, item_h), border_radius=10)
                    pygame.draw.rect(item_surf, (55, 85, 135, 130), (0, 0, card_w - 24, item_h), width=1, border_radius=10)

                author_color = (255, 220, 60) if is_sc else (0, 225, 255)
                sc_badge_str = f" [{amount}]" if is_sc else ""
                auth_pad_x = 14 if self.is_vertical else 10
                auth_pad_y = 6 if self.is_vertical else 6
                if self.is_vertical:
                    auth_sh = self.font_chat_author.render(f"{clean_author}{sc_badge_str}:", True, (0, 0, 0))
                    item_surf.blit(auth_sh, (auth_pad_x + 1, auth_pad_y + 1))
                auth_rend = self.font_chat_author.render(f"{clean_author}{sc_badge_str}:", True, author_color)
                item_surf.blit(auth_rend, (auth_pad_x, auth_pad_y))

                msg_color = (255, 250, 240) if is_sc else (235, 242, 255)
                msg_start_y = 38 if self.is_vertical else 30
                for line_idx, line_text in enumerate(display_lines):
                    if self.is_vertical:
                        line_sh = self.font_chat_msg.render(line_text, True, (0, 0, 0))
                        item_surf.blit(line_sh, (auth_pad_x + 1, msg_start_y + line_idx * line_h + 1))
                    line_rend = self.font_chat_msg.render(line_text, True, msg_color)
                    item_surf.blit(line_rend, (auth_pad_x, msg_start_y + line_idx * line_h))

                self.surf_chat_card.blit(item_surf, (12, y_offset))
                y_offset += item_h + (12 if self.is_vertical else 10)

        self.screen.blit(self.surf_chat_card, (card_x, card_y))

    def _draw_ai_subtitle_card(self, is_speaking: bool):
        """
        Draws AI Co-Host streaming response typewriter banner.
        16:9 Landscape: Bottom-center (w=1000, h=276, y=764).
        9:16 Vertical: Mid tier above chat (w=1000, h=328, y=796).
        """
        if self.is_vertical:
            card_w, card_h = 1000, 328
            card_x, card_y = (self.width - card_w) // 2, 796
        else:
            card_w, card_h = 1000, 276
            card_x, card_y = (self.width - card_w) // 2, self.height - card_h - 40

        self.surf_subtitle_card.fill((0, 0, 0, 0))
        pygame.draw.rect(self.surf_subtitle_card, (15, 20, 36, 230), (0, 0, card_w, card_h), border_radius=14)

        c_prim = tuple(int(c) for c in self.c_primary)
        pygame.draw.rect(self.surf_subtitle_card, (*c_prim, 200), (0, 0, card_w, card_h), width=2, border_radius=14)

        header_title = f"{self.cohost_name.upper()} (HOST)"
        title_rend = self.font_title.render(header_title, True, c_prim)
        title_y = 16 if self.is_vertical else 16
        self.surf_subtitle_card.blit(title_rend, (24, title_y))

        if is_speaking:
            pulse_alpha = int(128 + 127 * math.sin(self.time_elapsed * 8))
            dot_r = 7 if self.is_vertical else 6
            dot_surf = pygame.Surface((dot_r * 2 + 2, dot_r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(dot_surf, (0, 255, 180, pulse_alpha), (dot_r + 1, dot_r + 1), dot_r)
            speaking_lbl = self.font_badge.render("SPEAKING", True, (0, 255, 180))
            spk_w = speaking_lbl.get_width()
            self.surf_subtitle_card.blit(dot_surf, (card_w - 36, 25 if not self.is_vertical else 26))
            self.surf_subtitle_card.blit(speaking_lbl, (card_w - spk_w - 46, 22 if not self.is_vertical else 20))

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
        max_text_w = card_w - (60 if self.is_vertical else 50)
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

        max_lines = 5
        line_h = 48 if self.is_vertical else 36
        y_start = 74 if self.is_vertical else 64
        for i, line in enumerate(lines[:max_lines]):
            if self.is_vertical:
                line_sh = self.font_ai_subtitle.render(line, True, (0, 0, 0))
                self.surf_subtitle_card.blit(line_sh, (26, y_start + i * line_h + 2))
            line_rend = self.font_ai_subtitle.render(line, True, (245, 250, 255))
            self.surf_subtitle_card.blit(line_rend, (24, y_start + i * line_h))

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
            card_w, card_h = 860, 175
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
        Draws the 'Ask Your Questions Now!' celestial callout card:
        - Deep space sapphire glassmorphic container with radiant gold/cyan border
        - Top centered 'DIVINE Q&A LIVE' badge tag
        - Centered title row with celestial sunbeam question glyph + massive bold title
        - Centered high-legibility subtitle
        - Shimmering specular rim sweep & corner glints
        """
        # 1. Glassmorphism Card Frame
        bg_alpha = int(255 * alpha_mult) if self.is_vertical else min(248, int(245 * alpha_mult))
        pygame.draw.rect(surf, (10, 16, 32, bg_alpha), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(surf, (20, 36, 68, min(240, int(230 * alpha_mult))), (2, 2, w - 4, h - 4), border_radius=14)

        # Radiant Golden/Cyan Border Glow
        border_pulse = 0.85 + 0.15 * math.sin(t * 5.0)
        gold_border = (255, 215, 0)
        pygame.draw.rect(surf, (*gold_border, min(255, int(200 * border_pulse * alpha_mult))), (0, 0, w, h), width=2, border_radius=16)

        # Top rim specular sheen
        pygame.draw.line(surf, (255, 255, 255, min(255, int(160 * alpha_mult))), (24, 2), (w - 24, 2), 1)

        # 2. Top Pill Tag: "DIVINE Q&A LIVE" (Centered)
        tag_txt = self.font_callout_tag.render("DIVINE Q&A LIVE", True, (0, 240, 255))
        tag_w = tag_txt.get_width() + (40 if self.is_vertical else 34)
        tag_h = 28 if self.is_vertical else 22
        tag_x = (w - tag_w) // 2
        tag_y = 14 if self.is_vertical else 12

        pygame.draw.rect(surf, (0, 200, 255, min(255, int(50 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), border_radius=tag_h // 2)
        pygame.draw.rect(surf, (0, 240, 255, min(255, int(180 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), width=1, border_radius=tag_h // 2)

        # Pulsating Live Cyan Dot
        dot_a = min(255, int((160 + 95 * math.sin(t * 6.0)) * alpha_mult))
        dot_r = 5 if self.is_vertical else 4
        pygame.draw.circle(surf, (0, 255, 200, dot_a), (tag_x + 14, tag_y + tag_h // 2), dot_r)
        surf.blit(tag_txt, (tag_x + (26 if self.is_vertical else 22), tag_y + (3 if self.is_vertical else 2)))

        # 3. Middle Title Row: Celestial Question Badge + Title (Centered Lockup)
        title_str = "Ask Your Questions Now!"
        title_rend = self.font_callout_title.render(title_str, True, (255, 250, 230))
        sh_rend = self.font_callout_title.render(title_str, True, (180, 140, 20))

        badge_r = 21 if self.is_vertical else 17
        lockup_gap = 14
        total_title_w = (badge_r * 2 + 8) + lockup_gap + title_rend.get_width()
        lockup_x = (w - total_title_w) // 2
        badge_cx = lockup_x + badge_r + 4
        badge_cy = 70 if self.is_vertical else 58
        title_x = lockup_x + (badge_r * 2 + 8) + lockup_gap
        title_y = 51 if self.is_vertical else 41

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
        sub_str = "Drop your questions in chat • Divine wisdom & occassional roasting"
        sub_rend = self.font_callout_sub.render(sub_str, True, (195, 225, 255))
        sub_x = (w - sub_rend.get_width()) // 2
        sub_y = 118 if self.is_vertical else 96
        if self.is_vertical:
            sh_sub = self.font_callout_sub.render(sub_str, True, (0, 0, 0))
            surf.blit(sh_sub, (sub_x + 2, sub_y + 2))
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
        bg_alpha = int(255 * alpha_mult) if self.is_vertical else min(248, int(245 * alpha_mult))
        pygame.draw.rect(surf, (24, 10, 20, bg_alpha), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(surf, (48, 16, 34, min(240, int(230 * alpha_mult))), (2, 2, w - 4, h - 4), border_radius=14)

        # Radiant Neon Coral/Ruby Border Glow
        border_pulse = 0.85 + 0.15 * math.sin(t * 5.0)
        coral_border = (255, 50, 90)
        pygame.draw.rect(surf, (*coral_border, min(255, int(200 * border_pulse * alpha_mult))), (0, 0, w, h), width=2, border_radius=16)

        # Top rim specular sheen
        pygame.draw.line(surf, (255, 220, 230, min(255, int(160 * alpha_mult))), (24, 2), (w - 24, 2), 1)

        # 2. Top Pill Tag: "COMMUNITY HYPE" (Centered)
        tag_txt = self.font_callout_tag.render("COMMUNITY HYPE", True, (255, 100, 130))
        tag_w = tag_txt.get_width() + (40 if self.is_vertical else 34)
        tag_h = 28 if self.is_vertical else 22
        tag_x = (w - tag_w) // 2
        tag_y = 14 if self.is_vertical else 12

        pygame.draw.rect(surf, (255, 40, 80, min(255, int(50 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), border_radius=tag_h // 2)
        pygame.draw.rect(surf, (255, 60, 100, min(255, int(180 * alpha_mult))), (tag_x, tag_y, tag_w, tag_h), width=1, border_radius=tag_h // 2)

        # Pulsating Live Red Dot
        dot_a = min(255, int((160 + 95 * math.sin(t * 6.0)) * alpha_mult))
        dot_r = 5 if self.is_vertical else 4
        pygame.draw.circle(surf, (255, 50, 90, dot_a), (tag_x + 14, tag_y + tag_h // 2), dot_r)
        surf.blit(tag_txt, (tag_x + (26 if self.is_vertical else 22), tag_y + (3 if self.is_vertical else 2)))

        # 3. Middle Title Row: YouTube & Bell Badge + Title (Centered Lockup)
        title_str = "Like & Subscribe!"
        title_rend = self.font_callout_title.render(title_str, True, (255, 245, 245))
        sh_rend = self.font_callout_title.render(title_str, True, (160, 20, 50))

        pill_w, pill_h = (54, 34) if self.is_vertical else (44, 28)
        badge_area_w = pill_w + (18 if self.is_vertical else 14)
        lockup_gap = 14
        total_title_w = badge_area_w + lockup_gap + title_rend.get_width()
        lockup_x = (w - total_title_w) // 2

        # YouTube Red Squircle Pill
        pill_x = lockup_x
        pill_y = 54 if self.is_vertical else 44
        pygame.draw.rect(surf, (255, 20, 50, min(255, int(240 * alpha_mult))), (pill_x, pill_y, pill_w, pill_h), border_radius=8)
        pygame.draw.rect(surf, (255, 255, 255, min(255, int(180 * alpha_mult))), (pill_x, pill_y, pill_w, pill_h), width=1, border_radius=8)

        # White play triangle inside pill
        if self.is_vertical:
            tri_pts = [
                (pill_x + 20, pill_y + 9),
                (pill_x + 20, pill_y + 25),
                (pill_x + 37, pill_y + 17),
            ]
        else:
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
        bell_r = 16 if self.is_vertical else 13

        # Bell pill background
        pygame.draw.circle(surf, (35, 15, 25, min(255, int(240 * alpha_mult))), (bell_cx, bell_cy), bell_r)
        pygame.draw.circle(surf, (255, 200, 50, min(255, int(220 * alpha_mult))), (bell_cx, bell_cy), bell_r, 1)

        # Bell Dome
        dome_w = 8 if self.is_vertical else 6
        dome_h = 7 if self.is_vertical else 5
        bell_pts = [
            (bell_cx - dome_w, bell_cy + 4),
            (bell_cx - 4, bell_cy - dome_h),
            (bell_cx + 4, bell_cy - dome_h),
            (bell_cx + dome_w, bell_cy + 4),
        ]
        pygame.draw.polygon(surf, (255, 215, 0, min(255, int(245 * alpha_mult))), bell_pts)
        pygame.draw.circle(surf, (255, 240, 120, min(255, int(250 * alpha_mult))), (clapper_x, bell_cy + 6), 3)

        # Sound arcs around ringing bell
        if abs(swing) > 0.35:
            arc_a = min(255, int(abs(swing) * 210 * alpha_mult))
            pygame.draw.arc(surf, (255, 200, 50, arc_a), (bell_cx - 14, bell_cy - 7, 8, 13), math.pi * 0.6, math.pi * 1.4, 2)
            pygame.draw.arc(surf, (255, 200, 50, arc_a), (bell_cx + 6, bell_cy - 7, 8, 13), -math.pi * 0.4, math.pi * 0.4, 2)

        # Title Blit
        title_x = lockup_x + badge_area_w + lockup_gap
        title_y = 51 if self.is_vertical else 41
        surf.blit(sh_rend, (title_x + 2, title_y + 2))
        surf.blit(title_rend, (title_x, title_y))

        # 4. Bottom Subtitle Row (Centered)
        sub_str = "Smash like & ring bell for live stream alerts!"
        sub_rend = self.font_callout_sub.render(sub_str, True, (255, 220, 205))
        sub_x = (w - sub_rend.get_width()) // 2
        sub_y = 118 if self.is_vertical else 96
        if self.is_vertical:
            sh_sub = self.font_callout_sub.render(sub_str, True, (0, 0, 0))
            surf.blit(sh_sub, (sub_x + 2, sub_y + 2))
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


