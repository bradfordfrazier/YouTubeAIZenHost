"""
GPU-Accelerated 1920x1080 @ 60 FPS Visualizer Canvas for AI Live Stream Co-Host.
Features dynamic mood-driven particle/gradient background shaders,
audio spectrum FFT & hologram core reactivity, and glassmorphism broadcast HUD overlays.
"""

import json
import logging
import math
import os
from pathlib import Path
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pygame

from config import config

logger = logging.getLogger("AI-BRAIN")

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
        "savage": {
            "bg_dark": (24, 8, 14),
            "bg_accent": (75, 12, 35),
            "primary": (255, 40, 70),
            "secondary": (180, 20, 240),
            "highlight": (255, 210, 150),
            "glow": (255, 40, 70, 85),
            "speed": 1.7,
        },
        "laughing": {
            "bg_dark": (22, 14, 10),
            "bg_accent": (70, 40, 15),
            "primary": (255, 200, 30),
            "secondary": (255, 90, 60),
            "highlight": (255, 255, 200),
            "glow": (255, 180, 20, 80),
            "speed": 1.6,
        },
        "deadpan": {
            "bg_dark": (14, 16, 20),
            "bg_accent": (32, 38, 48),
            "primary": (140, 180, 215),
            "secondary": (90, 130, 160),
            "highlight": (220, 235, 245),
            "glow": (140, 180, 215, 45),
            "speed": 0.4,
        },
        "shocked": {
            "bg_dark": (18, 10, 34),
            "bg_accent": (60, 20, 95),
            "primary": (160, 70, 255),
            "secondary": (0, 255, 255),
            "highlight": (255, 255, 255),
            "glow": (160, 70, 255, 90),
            "speed": 2.2,
        },
        "curious": {
            "bg_dark": (10, 20, 24),
            "bg_accent": (20, 50, 60),
            "primary": (0, 230, 220),
            "secondary": (40, 220, 140),
            "highlight": (200, 255, 250),
            "glow": (0, 230, 220, 70),
            "speed": 1.0,
        },
        "neutral": {
            "bg_dark": (12, 16, 26),
            "bg_accent": (28, 40, 65),
            "primary": (100, 180, 255),
            "secondary": (130, 120, 210),
            "highlight": (235, 245, 255),
            "glow": (100, 180, 255, 60),
            "speed": 0.7,
        },
    }

    @classmethod
    def get(cls, mood: str) -> Dict:
        return cls.PALETTES.get(mood.lower(), cls.PALETTES["neutral"])


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
        self.sample_rate = self.cfg.tts_sample_rate
        self.host_name = self.cfg.ai_host_name
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

        # Position window safely at (40, 40) initially if not headless
        os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "40,40")

        pygame.init()
        pygame.font.init()

        self.should_quit = False
        if self.cfg.visualizer_headless:
            self.window_surf = None
            self.screen = pygame.Surface((self.width, self.height))
            self.window_size = (self.width, self.height)
        else:
            if self.cfg.visualizer_native_window:
                win_w = window_width or self.width
                win_h = window_height or self.height
            else:
                default_win_w = 540 if self.is_vertical else 320
                default_win_h = 960 if self.is_vertical else 180
                cfg_w = self.cfg.visualizer_window_width
                cfg_h = self.cfg.visualizer_window_height
                if cfg_w and cfg_h and ((cfg_h > cfg_w) == self.is_vertical):
                    win_w = window_width or cfg_w
                    win_h = window_height or cfg_h
                else:
                    win_w = window_width or default_win_w
                    win_h = window_height or default_win_h
            self.window_size = (win_w, win_h)
            flags = pygame.DOUBLEBUF | pygame.RESIZABLE
            if self.cfg.visualizer_borderless:
                flags = pygame.DOUBLEBUF | pygame.NOFRAME
            self.window_surf = pygame.display.set_mode(self.window_size, flags)
            pygame.event.set_grab(False)
            pygame.mouse.set_visible(True)
            caption_mode = "Vertical 9:16 (1080x1920)" if self.is_vertical else "Landscape 16:9 (1920x1080)"
            pygame.display.set_caption(f"AI Host Broadcast Visualizer - {caption_mode}")

            # On Windows, ensure window is 100% inside the visible monitor work area without hanging off boundaries
            if os.name == "nt":
                try:
                    import ctypes
                    from ctypes import wintypes
                    hwnd = pygame.display.get_wm_info().get("window")
                    if hwnd:
                        class MONITORINFO(ctypes.Structure):
                            _fields_ = [
                                ("cbSize", wintypes.DWORD),
                                ("rcMonitor", wintypes.RECT),
                                ("rcWork", wintypes.RECT),
                                ("dwFlags", wintypes.DWORD),
                            ]
                        hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
                        mi = MONITORINFO()
                        mi.cbSize = ctypes.sizeof(MONITORINFO)
                        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                            work = mi.rcWork
                            cfg_x = self.cfg.visualizer_window_x
                            cfg_y = self.cfg.visualizer_window_y
                            target_x = cfg_x if cfg_x is not None else (work.left + 40)
                            target_y = cfg_y if cfg_y is not None else (work.top + 40)

                            rect = wintypes.RECT(0, 0, win_w, win_h)
                            style = ctypes.windll.user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
                            ctypes.windll.user32.AdjustWindowRect(ctypes.byref(rect), style, False)
                            outer_w = rect.right - rect.left
                            outer_h = rect.bottom - rect.top

                            safe_x = min(max(work.left, target_x), max(work.left, work.right - outer_w))
                            safe_y = min(max(work.top, target_y), max(work.top, work.bottom - outer_h))
                            ctypes.windll.user32.SetWindowPos(hwnd, 0, safe_x, safe_y, outer_w, outer_h, 0x0004 | 0x0020)
                except Exception:
                    pass

            logger.info(
                f"Visualizer desktop window initialized: {self.window_size[0]}x{self.window_size[1]} "
                f"(Internal broadcast canvas: {self.width}x{self.height} @ 60 FPS)"
            )

            # Internal full-resolution rendering surface (always full 1080x1920 or 1920x1080 for NDI)
            self.screen = pygame.Surface((self.width, self.height))

        self.clock = pygame.time.Clock()

        # Resolution-Aware High-Legibility Typography
        if self.is_vertical:
            self.font_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 34, bold=True)
            self.font_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 26, bold=True)
            self.font_ai_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 36, bold=True)
            self.font_small = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 18)
            self.font_badge = pygame.font.SysFont("Consolas, Segoe UI, sans-serif", 24, bold=True)
            self.font_chat_author = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 30, bold=True)
            self.font_chat_msg = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 28, bold=True)
            self.font_god_badge = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 26, bold=True)
            self.font_callout_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 34, bold=True)
            self.font_callout_sub = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 20, bold=True)
            self.font_callout_tag = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 18, bold=True)
            self.font_callout_icon = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 30, bold=True)
        else:
            self.font_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 28, bold=True)
            self.font_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 22)
            self.font_ai_subtitle = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 34, bold=True)
            self.font_small = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 16)
            self.font_badge = pygame.font.SysFont("Consolas, Segoe UI, sans-serif", 18, bold=True)
            self.font_chat_author = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 24, bold=True)
            self.font_chat_msg = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 22, bold=True)
            self.font_god_badge = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 24, bold=True)
            self.font_callout_title = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 30, bold=True)
            self.font_callout_sub = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 18, bold=True)
            self.font_callout_tag = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 16, bold=True)
            self.font_callout_icon = pygame.font.SysFont("Segoe UI, Arial, sans-serif", 26, bold=True)

        # Ambient Particle System (optimally tuned for 60+ FPS on Intel Core i5 / UHD 630 Graphics)
        self.num_particles = self.cfg.visualizer_particle_count
        self.particles = [Particle(self.width, self.height) for _ in range(self.num_particles)]

        # Celestial Sparkle System around the central Point of Light
        self.core_cx = self.width // 2
        self.core_cy = 454 if self.is_vertical else 258
        self.num_sparkles = 25
        self.celestial_sparkles = [
            CelestialSparkle(self.core_cx, self.core_cy) for _ in range(self.num_sparkles)
        ]

        # Celebration Fireworks & Confetti Burst System
        self.celebration_particles: List[CelebrationParticle] = []
        self.celebration_timer: float = 0.0

        # Promotional Callout Overlays ("Ask God", "Like & Subscribe")
        self.promo_enabled = self.cfg.promo_overlay_enabled
        self.promo_mode = self.cfg.promo_mode.strip().lower()
        self.promo_interval = self.cfg.promo_overlay_interval_sec
        self.promo_duration = self.cfg.promo_overlay_duration_sec
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
        self.speech_intensity = 0.0  # Smooth continuous speech excitation envelope (0.0=idle, 1.0=speaking)
        self.subtitle_display_text = ""
        self.subtitle_target_text = ""
        self.typewriter_index = 0
        self.is_empty_hold = False
        self.active_question_text = ""
        self.active_question_author = ""
        self.active_question_is_sc = False
        self.active_question_is_cast = False
        self.active_question_amount = ""
        self.last_completed_question_text = ""
        self.active_question_start_time = 0.0
        self.question_fade_alpha = 0.0
        self.question_fade_timer = 0.0
        self.question_fade_state = "idle"  # "fade_in", "steady", "fade_out", "idle"
        self.question_y_drift = 0.0
        self._active_pinned_message: Optional[Dict] = None

        # Ethereal consciousness text transition engine (arising from nowhere & dissolving into nowhere)
        motto = self.cfg.motto_phrase
        self.ai_text_current = motto
        self.ai_text_target = motto
        self.ai_text_alpha = 1.0          # Start with motto visible when there is nothing to display
        self.ai_text_state = "steady"
        self.ai_text_y_drift = 0.0
        self.motto_pause_timer = 0.0

        # Live chat pinned question card animation state (synchronized dissolution with Oracle comment)
        self.pinned_chat_alpha = 0.0
        self.pinned_chat_state = "idle"  # "fade_in", "steady", "fade_out", "idle"
        self.pinned_chat_stored: Optional[Dict] = None

        # Pre-render high-resolution multi-layer radial corona / bloom sprites for all moods
        # Inside bright circle scaled to half size (~85px when scaled to 228px visualizer core)
        self._bloom_sprites = {}
        sprite_sz = 256
        half_sz = sprite_sz // 2
        core_sz = int(half_sz * 0.38)
        for mood_key, p_val in ColorPalette.PALETTES.items():
            spr = pygame.Surface((sprite_sz, sprite_sz), pygame.SRCALPHA)
            c_p = p_val["primary"]
            c_h = p_val["highlight"]
            for r in range(half_sz, 0, -2):
                if r > core_sz:
                    # Outer disc falloff
                    t_out = (half_sz - r) / (half_sz - core_sz)
                    alpha = int((t_out ** 2.0) * 30)
                    col = (*c_p, alpha)
                else:
                    # Inside circle: bright light-cyan highlight core scaled to half size
                    t_in = (core_sz - r) / core_sz
                    alpha = int(30 + (t_in ** 2.0) * 200)
                    col = (
                        int(c_p[0] * (1.0 - t_in) + c_h[0] * t_in),
                        int(c_p[1] * (1.0 - t_in) + c_h[1] * t_in),
                        int(c_p[2] * (1.0 - t_in) + c_h[2] * t_in),
                        alpha,
                    )
                pygame.draw.circle(spr, col, (half_sz, half_sz), r)
            self._bloom_sprites[mood_key] = spr

        # Tightly-bounded scratch surfaces for maximum memory bandwidth efficiency on UHD Graphics
        self.box_size = 560
        self.surf_flare = pygame.Surface((self.box_size, self.box_size), pygame.SRCALPHA)

        # Adaptive card dimensions with left and right margin padding
        chat_w, chat_h = (940, 580) if self.is_vertical else (380, 490)
        sub_w, sub_h = (940, 380) if self.is_vertical else (880, 360)
        promo_w, promo_h = (920, 130) if self.is_vertical else (820, 114)

        self.surf_chat_card = pygame.Surface((chat_w, chat_h), pygame.SRCALPHA)
        self.surf_subtitle_card = pygame.Surface((sub_w, sub_h), pygame.SRCALPHA)
        self.surf_ai_text = pygame.Surface((sub_w, sub_h), pygame.SRCALPHA)
        self.surf_promo_card = pygame.Surface((promo_w, promo_h), pygame.SRCALPHA)
        self._surf_god_circles = pygame.Surface((600, 600), pygame.SRCALPHA)
        self._last_preview_flip_time = 0.0
        self._text_cache: Dict[Tuple, pygame.Surface] = {}
        self.current_palette = ColorPalette.get(self.current_mood)

        # Fallback chat history cache for instant restoration on visualizer startup
        self._cached_chat_messages: List[Dict] = []
        self._load_cached_chat()

    def _render_text(self, font: pygame.font.Font, text: str, color: Any) -> pygame.Surface:
        """Cached font rendering helper to eliminate redundant surface allocations per frame."""
        c_tuple = tuple(int(x) for x in color[:3]) if isinstance(color, (list, tuple, np.ndarray)) else color
        key = (id(font), text, c_tuple)
        surf = self._text_cache.get(key)
        if surf is None:
            surf = font.render(text, True, color)
            if len(self._text_cache) > 2000:
                self._text_cache.clear()
            self._text_cache[key] = surf
        return surf

    def _load_cached_chat(self):
        """Restores recent chat history from disk so visualizer resumes seamlessly on restart."""
        cache_file = Path(__file__).resolve().parent / "chat_cache.json"
        if not cache_file.exists():
            return
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._cached_chat_messages = [
                    item for item in data[-50:]
                    if isinstance(item, dict) and "author" in item and "message" in item
                ]
                if self._cached_chat_messages:
                    logger.info(f"📂 [Visualizer] Restored {len(self._cached_chat_messages)} chat messages from cache into chat panel.")
        except Exception as e:
            logger.debug(f"Failed to load visualizer chat cache: {e}")

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
        m_lower = (mood or "neutral").strip().lower()
        if m_lower not in ColorPalette.PALETTES:
            m_lower = "neutral"
        if m_lower != self.target_mood:
            self.target_mood = m_lower
            self.mood_lerp_factor = 0.0

    def fade_out_for_turn(self):
        """
        Immediately initiates smooth fade-out of whatever is currently on screen
        (motto or previous comment) to prepare a clean canvas for an incoming speech turn.
        Unlike clear_subtitle(), this transitions directly to idle_empty once faded out,
        preventing any motto pause or re-emergence before speech starts.
        """
        self.is_empty_hold = False
        self.subtitle_target_text = ""
        self.ai_text_target = ""
        if self.ai_text_current and self.ai_text_alpha > 0.01:
            self.ai_text_state = "fade_out"
            self.pinned_chat_state = "fade_out"
        else:
            self.ai_text_current = ""
            self.ai_text_alpha = 0.0
            self.ai_text_state = "idle_empty"

        # If promo overlay is currently active or entering/displaying, smoothly transition it to exit without jumping
        if self.promo_state in ("entrance", "display"):
            self.promo_state = "exit"
            self.promo_state_timer = 0.0
            self.promo_slide_factor = 0.0

    def fade_out_question(self):
        """Initiates smooth graceful fade-out of the active question preview in the main comment card."""
        if self.question_fade_state in ("fade_in", "steady"):
            self.question_fade_state = "fade_out"
            self.question_fade_timer = 0.0

    def clear_subtitle(self):
        """Resets subtitle text to motto, initiating smooth synchronized dissolution of Oracle comment & pinned question."""
        self.is_empty_hold = False
        self.subtitle_target_text = ""
        motto = self.cfg.motto_phrase
        self.ai_text_target = motto
        if self.ai_text_current and self.ai_text_current != motto and self.ai_text_alpha > 0.01:
            self.ai_text_state = "fade_out"
            self.pinned_chat_state = "fade_out"
        elif self.ai_text_state in ("motto_pause", "fade_out"):
            pass
        elif self.ai_text_current == motto and self.ai_text_alpha > 0.01:
            self.ai_text_state = "steady"
            self.ai_text_alpha = 1.0
        else:
            self.ai_text_current = ""
            self.ai_text_alpha = 0.0
            motto_delay = max(0.0, self.cfg.motto_pre_fade_in_sec)
            if motto_delay > 0.0:
                self.ai_text_state = "motto_pause"
                self.motto_pause_timer = motto_delay
            else:
                self.ai_text_current = motto
                self.ai_text_state = "fade_in"
                self.ai_text_y_drift = 6.0
            self._active_pinned_message = None

    def set_pinned(self, message: Optional[Dict]):
        """Explicitly sets or updates the active pinned chat message."""
        self._active_pinned_message = message
        if message and isinstance(message, dict):
            msg = message.get("message", "").strip()
            if msg and msg == self.last_completed_question_text:
                self.last_completed_question_text = ""

    def clear_pinned(self):
        """Explicitly clears the active pinned chat message."""
        self._active_pinned_message = None

    def set_subtitle(self, text: str):
        """Update AI co-host speaking subtitle text with clean ethereal emergence."""
        clean = re.sub(r"@+", "@", text).strip() if text else ""
        logger.debug(f"✨ [Visualizer] set_subtitle called: '{clean[:40]}'")
        if self.cfg.vox_only_mode:
            self.subtitle_target_text = ""
            return

        if not clean or len(clean) < 4:
            self.subtitle_target_text = ""
            return

        self.is_empty_hold = False
        if clean != self.subtitle_target_text:
            self.subtitle_target_text = clean
            # When switching to a new utterance, start cleanly from alpha 0.0
            self.ai_text_current = clean
            self.ai_text_target = clean
            self.ai_text_alpha = 0.0
            self.ai_text_state = "fade_in"
            self.ai_text_y_drift = 6.0

            # Ensure promo overlay smoothly exits if active when speech begins
            if self.promo_state in ("entrance", "display"):
                self.promo_state = "exit"
                self.promo_state_timer = 0.0
                self.promo_slide_factor = 0.0

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
                self.current_palette = ColorPalette.get(self.current_mood)

    @property
    def cohost_name(self) -> str:
        return self.host_name

    def render_frame(
        self,
        audio_metrics: Dict,
        chat_messages: List[Dict],
        obs_connected: bool = True,
        engagement_mode: str = "active",
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
        pinned_chat_message: Optional[Dict] = None,
        ai_subtitle: Optional[str] = None,
    ) -> bytes:
        """
        Renders a full 1080p60 frame and returns the RGBA byte buffer.
        """
        dt = 1.0 / self.fps
        self.time_elapsed += dt
        self._update_palette_lerp(dt)
        if ai_subtitle:
            self.set_subtitle(ai_subtitle)

        # Extract audio metrics
        rms = audio_metrics.get("rms", 0.0)
        spectrum = audio_metrics.get("spectrum", np.zeros(32, dtype=np.float32))
        is_speaking = audio_metrics.get("is_speaking", False)

        # Smooth speech excitation envelope tracking (fast attack, organic smooth decay)
        target_intensity = 1.0 if is_speaking else 0.0
        if is_speaking:
            self.speech_intensity += (target_intensity - self.speech_intensity) * min(1.0, dt * 10.0)
        else:
            self.speech_intensity += (target_intensity - self.speech_intensity) * min(1.0, dt * 3.5)

        # 1. Background Gradient & Wave Ribbons
        self._draw_dynamic_background(rms)

        # 2. Particle Field
        p_info = self.current_palette
        speed_mult = p_info["speed"]
        self._draw_particles(speed_mult, rms)

        # 3. Brightly Glistening and Shining Point of Light (God / The Source) & FFT Spectrum
        self._draw_hologram_core(rms, spectrum, is_speaking)

        # 4. Celebration Fireworks & Confetti Shower
        self._draw_celebration_fx(dt)

        # 5. Glassmorphism HUD Overlays
        if self.cfg.show_top_status_bar:
            self._draw_top_header(
                obs_connected=obs_connected,
                engagement_mode=engagement_mode,
                concurrent_viewers=concurrent_viewers,
                is_stream_live=is_stream_live,
            )

        # Maintain active pinned message in chat panel until Oracle response completely dissolves
        motto = self.cfg.motto_phrase
        has_active_statement = bool(
            is_speaking
            or (self.subtitle_target_text and self.subtitle_target_text != motto)
            or (self.ai_text_current and self.ai_text_current != motto and self.ai_text_alpha > 0.05)
        )

        if pinned_chat_message and isinstance(pinned_chat_message, dict):
            self._active_pinned_message = pinned_chat_message
        elif not has_active_statement:
            self._active_pinned_message = None

        effective_pinned_chat = pinned_chat_message or self._active_pinned_message
        self._draw_live_chat_card(chat_messages, pinned_message=effective_pinned_chat)
        self._draw_ai_subtitle_card(
            is_speaking=is_speaking,
            concurrent_viewers=concurrent_viewers,
            pinned_chat_message=effective_pinned_chat,
        )

        # For promo callout suppression, only actively speaking or newly targeted incoming turns are considered busy.
        # Fading out a completed turn into empty/motto does NOT suppress or abort promo overlays.
        has_active_incoming_turn = bool(
            is_speaking
            or (self.subtitle_target_text and self.subtitle_target_text != motto)
            or (pinned_chat_message and self.question_fade_state in ("fade_in", "steady"))
        )
        is_promo_suppressed = is_speaking or has_active_incoming_turn

        # 6. Periodic Fun Promotional Graphic Overlays ("Ask God" & "Like & Subscribe")
        self._draw_promo_callout_overlay(dt, is_speaking=is_speaking, is_turn_busy=is_promo_suppressed)

        # Update Pygame display if not headless (operator preview window)
        if not self.cfg.visualizer_headless and self.window_surf is not None:
            # Handle window events (resize, quit, etc.)
            for event in pygame.event.get():
                if event.type == pygame.VIDEORESIZE:
                    self.window_size = (max(160, event.w), max(90, event.h))
                    flags = pygame.DOUBLEBUF | pygame.RESIZABLE
                    if self.cfg.visualizer_borderless:
                        flags = pygame.DOUBLEBUF | pygame.NOFRAME
                    self.window_surf = pygame.display.set_mode(self.window_size, flags)
                    pygame.event.set_grab(False)
                    pygame.mouse.set_visible(True)
                elif event.type == pygame.QUIT:
                    self.should_quit = True

            # Scale and flip preview window at <= 30 FPS to reduce CPU/memory load while NDI stays 60 FPS
            now_perf = time.perf_counter()
            if (now_perf - self._last_preview_flip_time) >= 0.033:
                self._last_preview_flip_time = now_perf
                if self.window_size == (self.width, self.height):
                    self.window_surf.blit(self.screen, (0, 0))
                else:
                    pygame.transform.scale(self.screen, self.window_size, self.window_surf)
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



        # Flowing sine wave ribbons in lower half (drawn directly on canvas)
        c_sec = tuple(int(c) for c in self.c_secondary)
        num_waves = 3
        base_y_start = 1530 if self.is_vertical else 580
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
        self.light_rotation += 0.003 + (rms * 0.04 * self.speech_intensity)

        c_prim = tuple(int(c) for c in self.c_primary)
        c_sec = tuple(int(c) for c in self.c_secondary)
        c_high = tuple(int(c) for c in self.c_highlight)
        c_pure_white = (255, 255, 255)
        c_gold_white = (255, 250, 230)

        # Smooth speech excitation factor:
        # On active words: scales with RMS audio power
        # In between words while speaking: sits at comfortable baseline (0.3)
        # When speech finishes: smoothly decays from 0.3 down to 0.0 over ~0.7s without any step discontinuities
        speak_boost = (rms * (1.0 + self.speech_intensity * 1.5)) + (self.speech_intensity * 0.3)

        # ----------------------------------------------------------------------
        # 1. Concentric Celestial God Circles (Complete Circle & Inner Circle)
        # ----------------------------------------------------------------------
        idle_breathe = 2.5 * math.sin(self.time_elapsed * 0.9)
        r_outer = int(210 + speak_boost * 35 + idle_breathe)
        r_inner = r_outer // 2  # About half the size of the complete circle

        # Draw into persistent fixed-size scratch surface without per-frame reallocation
        self._surf_god_circles.fill((0, 0, 0, 0))
        center_circle = (300, 300)

        # A. The Complete Circle: Very transparent but still clearly visible
        alpha_outer = int(38 + rms * 20)
        pygame.draw.circle(self._surf_god_circles, (*c_prim, alpha_outer), center_circle, r_outer)
        pygame.draw.circle(self._surf_god_circles, (*c_high, min(255, alpha_outer + 25)), center_circle, r_outer, 1)

        # B. The Inner Circle: About half the size and more solid
        alpha_inner = int(145 + speak_boost * 35)
        pygame.draw.circle(self._surf_god_circles, (*c_prim, alpha_inner), center_circle, r_inner)
        pygame.draw.circle(self._surf_god_circles, (*c_high, min(255, alpha_inner + 40)), center_circle, int(r_inner * 0.72))
        pygame.draw.circle(self._surf_god_circles, (*c_high, min(255, alpha_inner + 50)), center_circle, r_inner, 1)

        # Both circles sit directly behind the gleaming point of light
        self.screen.blit(self._surf_god_circles, (cx - 300, cy - 300))

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
            active_shimmer = 0.84 + 0.16 * math.sin(self.time_elapsed * 8.5 + i * 1.57)
            idle_shimmer = 0.94 + 0.06 * math.sin(self.time_elapsed * 3.5 + i * 1.57)
            shimmer = idle_shimmer * (1.0 - self.speech_intensity) + active_shimmer * self.speech_intensity
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
            active_diag_shimmer = 0.82 + 0.18 * math.cos(self.time_elapsed * 9.5 + i * 2.1)
            idle_diag_shimmer = 0.94 + 0.06 * math.cos(self.time_elapsed * 3.8 + i * 2.1)
            shimmer = idle_diag_shimmer * (1.0 - self.speech_intensity) + active_diag_shimmer * self.speech_intensity
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
            active_tert_shimmer = 0.75 + 0.25 * math.sin(self.time_elapsed * 11.0 + i * 1.8)
            shimmer = 1.0 * (1.0 - self.speech_intensity) + active_tert_shimmer * self.speech_intensity
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
                s_size = int(spk.size + (rms * 2.0 * self.speech_intensity))
                pygame.draw.circle(self.surf_flare, (*c_high, s_alpha), (local_sx, local_sy), s_size)
                pygame.draw.circle(self.surf_flare, (*c_pure_white, min(255, s_alpha + 40)), (local_sx, local_sy), max(1, s_size // 2))

        self.screen.blit(self.surf_flare, (box_x, box_y), special_flags=pygame.BLEND_ADD)

        # ----------------------------------------------------------------------
        # 3. Ultra-Bright Center Singularity (Intense Photosphere Core)
        # ----------------------------------------------------------------------
        idle_core_pulse = 0.5 * math.sin(self.time_elapsed * 2.0)
        active_core_pulse = 2.5 * math.sin(self.time_elapsed * 8.0)
        blended_pulse = idle_core_pulse * (1.0 - self.speech_intensity) + active_core_pulse * self.speech_intensity
        r_singularity = int(9 + speak_boost * 8 + blended_pulse)
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
        badge_w, badge_h = (220, 48) if self.is_vertical else (220, 42)
        bx, by = cx - badge_w // 2, cy + (266 if self.is_vertical else 252)

        pygame.draw.rect(self.screen, (14, 20, 36), (bx, by, badge_w, badge_h), border_radius=badge_h // 2)
        pygame.draw.rect(self.screen, c_high, (bx, by, badge_w, badge_h), width=1, border_radius=badge_h // 2)

        label_str = f"•  {self.cohost_name.upper()}  •"
        label_rend = self._render_text(self.font_god_badge, label_str, c_high)
        self.screen.blit(label_rend, (cx - label_rend.get_width() // 2, by + (badge_h - label_rend.get_height()) // 2))

    def _draw_top_header(
        self,
        obs_connected: bool,
        engagement_mode: str = "active",
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
    ):
        """Draws broadcast status bar at top of screen directly on canvas."""
        if not self.cfg.show_top_status_bar:
            return
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
        live_txt = self._render_text(self.font_badge, badge_text, dot_color)
        self.screen.blit(live_txt, (48, txt_y))

        # Mood Badge
        c_prim = tuple(int(c) for c in self.c_primary)
        mood_txt = self._render_text(self.font_badge, f"MOOD: {self.current_mood.upper()}", c_prim)

        if self.is_vertical:
            self.screen.blit(mood_txt, (360, txt_y))
            ndi_txt = self._render_text(self.font_badge, "NDI: 9:16", (160, 200, 255))
            self.screen.blit(ndi_txt, (self.width - ndi_txt.get_width() - 30, txt_y))
        else:
            obs_color = (0, 240, 150) if obs_connected else (220, 180, 50)
            obs_txt = self._render_text(self.font_badge, f"OBS WS: {'ACTIVE' if obs_connected else 'WAITING'}", obs_color)
            self.screen.blit(obs_txt, (360, txt_y))
            self.screen.blit(mood_txt, (640, txt_y))
            ndi_txt = self._render_text(self.font_badge, f"NDI: {self.cfg.ndi_stream_name} (1080p60)", (160, 200, 255))
            self.screen.blit(ndi_txt, (self.width - ndi_txt.get_width() - 30, txt_y))

    def _draw_cast_badge(self, surface: pygame.Surface, x: int, y: int, alpha: float = 1.0) -> int:
        """
        Renders a distinctive glassmorphic [CAST] transparency pill badge.
        Returns total width consumed including padding.
        """
        badge_label = self.cfg.cast_badge_label
        badge_tag = f"{badge_label}"
        badge_txt = self._render_text(self.font_callout_tag, badge_tag, (240, 185, 255))

        pad_w = 6 if self.is_vertical else 5
        pad_h = 2 if self.is_vertical else 1
        badge_w = badge_txt.get_width() + (pad_w * 2)
        badge_h = badge_txt.get_height() + (pad_h * 2)

        pill_surf = pygame.Surface((badge_w, badge_h), pygame.SRCALPHA)
        # Background: deep glassmorphic purple
        pygame.draw.rect(pill_surf, (55, 20, 80, int(200 * alpha)), (0, 0, badge_w, badge_h), border_radius=4)
        # Border: vibrant neon purple accent
        pygame.draw.rect(pill_surf, (215, 140, 255, int(230 * alpha)), (0, 0, badge_w, badge_h), width=1, border_radius=4)
        pill_surf.blit(badge_txt, (pad_w, pad_h))
        if alpha < 0.999:
            pill_surf.set_alpha(int(np.clip(alpha * 255, 0, 255)))

        surface.blit(pill_surf, (x, y))
        return badge_w

    def _draw_live_chat_card(self, chat_messages: List[Dict], pinned_message: Optional[Dict] = None):
        """
        Draws YouTube Live Chat transparent overlay panel with support for pinned active question highlight:
        16:9 Landscape: Left column below center (w=380, h=490, x=60, y=482).
        9:16 Vertical: Bottom tier below AI Host (w=940, h=580, y=1205, up to 5 items).
        """
        if self.is_vertical:
            card_w, card_h = 940, 580
            card_x, card_y = (self.width - card_w) // 2, 1205
        else:
            card_w, card_h = 380, 490
            card_x, card_y = 60, 482

        self.surf_chat_card.fill((0, 0, 0, 0))

        # Header iconic graphic elements & typography
        pad_x = 24 if self.is_vertical else 18
        icon_x = pad_x
        icon_y = 16 if self.is_vertical else 12

        # 1. Iconic Vector Chat Bubble Icon (Gold bubble with speech tail and 2 inner dots)
        pygame.draw.rect(self.surf_chat_card, (255, 195, 60), (icon_x, icon_y + 1, 20, 15), border_radius=4)
        pygame.draw.polygon(
            self.surf_chat_card,
            (255, 195, 60),
            [(icon_x + 3, icon_y + 15), (icon_x + 9, icon_y + 15), (icon_x + 3, icon_y + 20)]
        )
        pygame.draw.circle(self.surf_chat_card, (15, 24, 46), (icon_x + 6, icon_y + 8), 2)
        pygame.draw.circle(self.surf_chat_card, (15, 24, 46), (icon_x + 14, icon_y + 8), 2)

        # "LIVE CHAT" Text
        text_x = icon_x + 28
        tag_txt_sh = self._render_text(self.font_badge, "LIVE CHAT", (0, 0, 0))
        tag_txt = self._render_text(self.font_badge, "LIVE CHAT", (255, 195, 60))
        self.surf_chat_card.blit(tag_txt_sh, (text_x + 1, icon_y + 1))
        self.surf_chat_card.blit(tag_txt, (text_x, icon_y))

        # 2. Iconic Pulsing Live Broadcast Glow Dot + "FEED" Label
        feed_lbl_sh = self._render_text(self.font_badge, "FEED", (0, 0, 0))
        feed_lbl = self._render_text(self.font_badge, "FEED", (0, 240, 150))
        feed_w = feed_lbl.get_width()
        feed_x = card_w - feed_w - pad_x
        feed_y = icon_y

        pulse_alpha = int(140 + 115 * math.sin(self.time_elapsed * 6.0))
        dot_surf = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(dot_surf, (0, 240, 150, pulse_alpha), (8, 8), 4)
        pygame.draw.circle(dot_surf, (255, 255, 255, min(255, pulse_alpha + 40)), (8, 8), 2)
        self.surf_chat_card.blit(dot_surf, (feed_x - 20, feed_y + 2))

        self.surf_chat_card.blit(feed_lbl_sh, (feed_x + 1, feed_y + 1))
        self.surf_chat_card.blit(feed_lbl, (feed_x, feed_y))

        y_offset = 64 if self.is_vertical else 48
        max_content_y = card_h - (14 if self.is_vertical else 12)
        line_h = 38 if self.is_vertical else 28
        auth_h = 36 if self.is_vertical else 32
        sh_off = 2 if self.is_vertical else 1

        # ----------------------------------------------------------------------
        # 3. ACTIVE CHAT QUESTION IDENTIFICATION & PIN DOCKING CALCULATION
        # ----------------------------------------------------------------------
        dt = 1.0 / self.fps
        comment_fade_in_sec = max(0.05, self.cfg.comment_fade_in_sec)
        comment_fade_out_sec = max(0.05, self.cfg.comment_fade_out_sec)
        pin_fade_in_rate = 1.0 / comment_fade_in_sec
        pin_fade_out_rate = 1.0 / comment_fade_out_sec

        if pinned_message and isinstance(pinned_message, dict):
            # Check if this is a newly selected pinned message
            is_new_pin = False
            if not self.pinned_chat_stored:
                is_new_pin = True
            else:
                old_a = self.pinned_chat_stored.get("author", "").strip().lower().lstrip("@")
                old_m = self.pinned_chat_stored.get("message", "").strip()
                new_a = pinned_message.get("author", "").strip().lower().lstrip("@")
                new_m = pinned_message.get("message", "").strip()
                if old_a != new_a or old_m != new_m:
                    is_new_pin = True

            self.pinned_chat_stored = pinned_message
            if is_new_pin:
                self.pinned_chat_state = "fade_in"
                self.pinned_chat_alpha = 0.0

            if self.pinned_chat_state != "steady":
                self.pinned_chat_state = "fade_in"
                self.pinned_chat_alpha = min(1.0, self.pinned_chat_alpha + dt * pin_fade_in_rate)
                if self.pinned_chat_alpha >= 1.0:
                    self.pinned_chat_alpha = 1.0
                    self.pinned_chat_state = "steady"
        else:
            if self.pinned_chat_state in ("fade_in", "steady"):
                self.pinned_chat_state = "fade_out"
            if self.pinned_chat_state == "fade_out":
                self.pinned_chat_alpha = max(0.0, self.pinned_chat_alpha - dt * pin_fade_out_rate)
                if self.pinned_chat_alpha <= 0.0:
                    self.pinned_chat_alpha = 0.0
                    self.pinned_chat_state = "idle"
                    self.pinned_chat_stored = None

        if chat_messages:
            self._cached_chat_messages = list(chat_messages)
        display_msgs = list(chat_messages) if chat_messages else list(self._cached_chat_messages)

        # Identify location of active question in the chat feed
        target_pin = self.pinned_chat_stored
        has_active_question = bool(self.pinned_chat_alpha > 0.005 and target_pin)
        active_auth = (target_pin.get("author", "").strip().lower().lstrip("@")) if has_active_question else ""
        active_msg = (target_pin.get("message", "").strip()) if has_active_question else ""

        active_idx = -1
        if has_active_question and display_msgs:
            for i in range(len(display_msgs) - 1, -1, -1):
                item_auth = display_msgs[i].get("author", "").strip().lower().lstrip("@")
                item_msg = display_msgs[i].get("message", "").strip()
                if item_auth == active_auth and (item_msg == active_msg or active_msg in item_msg or item_msg in active_msg):
                    active_idx = i
                    break

        # If active question was not found in display_msgs, append it to bottom so it's guaranteed to appear immediately!
        if has_active_question and active_idx == -1 and target_pin:
            display_msgs.append(target_pin)
            active_idx = len(display_msgs) - 1

        # Feed capacity: how many normal messages fit vertically in the card
        visible_feed_capacity = 5 if self.is_vertical else 4
        msgs_after_active = (len(display_msgs) - 1 - active_idx) if active_idx != -1 else 0

        # Pin at top once incoming messages push it to the top of visible card (or off the top)
        is_pinned_at_top = has_active_question and (msgs_after_active >= (visible_feed_capacity - 1))

        # ----------------------------------------------------------------------
        # 4. RENDER TOP PINNED CONTAINER (When Docked at Top)
        # ----------------------------------------------------------------------
        if is_pinned_at_top and target_pin:
            pin_raw_auth = target_pin.get("author", "Viewer").strip().lstrip("@")
            pin_clean_auth = f"@{pin_raw_auth.replace(' ', '')}"
            pin_msg = target_pin.get("message", "").strip()
            pin_is_sc = target_pin.get("is_superchat", False)
            pin_is_cast = target_pin.get("is_cast", False) or target_pin.get("author_type") == "cast"
            pin_amount = target_pin.get("amount", "")

            # Text wrapping for pinned message
            max_pin_text_w = card_w - (pad_x * 2 + 24)
            words = pin_msg.split(" ")
            pin_wrapped = []
            cur_l = ""
            for w in words:
                test_l = f"{cur_l} {w}".strip()
                if self.font_chat_msg.size(test_l)[0] < max_pin_text_w:
                    cur_l = test_l
                else:
                    if cur_l:
                        pin_wrapped.append(cur_l)
                    cur_l = w
            if cur_l:
                pin_wrapped.append(cur_l)
            display_pin_lines = pin_wrapped[:3] if pin_wrapped else [""]

            # Compute pinned card height
            pin_box_h = auth_h + (len(display_pin_lines) * line_h) + (14 if self.is_vertical else 10)
            pin_box_w = card_w - (pad_x * 2)

            # Colors for pinned container
            border_pulse = 0.85 + 0.15 * math.sin(self.time_elapsed * 5.0)
            if pin_is_sc:
                pin_border_col = (255, 215, 0)
                pin_auth_col = (255, 225, 60)
            elif pin_is_cast:
                pin_border_col = (215, 140, 255)
                pin_auth_col = (235, 170, 255)
            else:
                pin_border_col = (0, 240, 255)
                pin_auth_col = (100, 245, 255)

            # Glassmorphic glowing pinned background container with smooth alpha fading
            pin_alpha_int = int(np.clip(self.pinned_chat_alpha * 255, 0, 255))
            pin_surf = pygame.Surface((pin_box_w, pin_box_h), pygame.SRCALPHA)
            pygame.draw.rect(pin_surf, (14, 22, 42, int(240 * self.pinned_chat_alpha)), (0, 0, pin_box_w, pin_box_h), border_radius=12)
            pygame.draw.rect(pin_surf, (24, 40, 72, int(220 * self.pinned_chat_alpha)), (2, 2, pin_box_w - 4, pin_box_h - 4), border_radius=10)
            pygame.draw.rect(
                pin_surf,
                (*pin_border_col, int(220 * border_pulse * self.pinned_chat_alpha)),
                (0, 0, pin_box_w, pin_box_h),
                width=2,
                border_radius=12,
            )

            # Top right "PINNED QUESTION" badge pill inside pinned container
            pin_badge_tag = "PINNED QUESTION"
            pin_badge_txt = self._render_text(self.font_callout_tag, pin_badge_tag, (255, 215, 0))
            pin_badge_w = pin_badge_txt.get_width() + 16
            pin_badge_h = 20 if self.is_vertical else 18
            pin_badge_x = pin_box_w - pin_badge_w - 8
            pin_badge_y = 6
            pygame.draw.rect(pin_surf, (255, 215, 0, int(40 * self.pinned_chat_alpha)), (pin_badge_x, pin_badge_y, pin_badge_w, pin_badge_h), border_radius=4)
            pygame.draw.rect(pin_surf, (255, 215, 0, int(180 * self.pinned_chat_alpha)), (pin_badge_x, pin_badge_y, pin_badge_w, pin_badge_h), width=1, border_radius=4)
            pin_surf.blit(pin_badge_txt, (pin_badge_x + 8, pin_badge_y + (2 if self.is_vertical else 1)))

            # Author line inside pinned container (100% opaque text)
            pin_sc_str = f" [{pin_amount}]" if pin_is_sc else ""
            pin_auth_str = f"{pin_clean_auth}{pin_sc_str}:"
            auth_sh = self._render_text(self.font_chat_author, pin_auth_str, (0, 0, 0))
            auth_rend = self._render_text(self.font_chat_author, pin_auth_str, pin_auth_col)
            pin_surf.blit(auth_sh, (10 + sh_off, 6 + sh_off))
            pin_surf.blit(auth_rend, (10, 6))

            if pin_is_cast:
                pin_auth_w = self.font_chat_author.size(pin_auth_str)[0]
                badge_y = 6 + max(0, (auth_h - (self.font_callout_tag.get_height() + (4 if self.is_vertical else 2))) // 2)
                self._draw_cast_badge(pin_surf, 10 + pin_auth_w + 8, badge_y, alpha=self.pinned_chat_alpha)

            # Message lines inside pinned container (100% opaque text)
            msg_y_start = 6 + auth_h - (2 if self.is_vertical else 0)
            for idx, l_text in enumerate(display_pin_lines):
                line_y = msg_y_start + idx * line_h
                line_sh = self._render_text(self.font_chat_msg, l_text, (0, 0, 0))
                line_rend = self._render_text(self.font_chat_msg, l_text, (255, 255, 255))
                pin_surf.blit(line_sh, (10 + sh_off, line_y + sh_off))
                pin_surf.blit(line_rend, (10, line_y))

            self.surf_chat_card.blit(pin_surf, (pad_x, y_offset))
            y_offset += int(pin_box_h * self.pinned_chat_alpha) + (14 if self.is_vertical else 10)

        # ----------------------------------------------------------------------
        # 5. CHRONOLOGICAL LIVE CHAT MESSAGES (With In-Feed Row Highlight)
        # ----------------------------------------------------------------------
        if is_pinned_at_top:
            # Exclude active question from lower scrolling area to prevent duplicate display
            scrolling_msgs = [
                m for m in display_msgs
                if not (
                    m.get("author", "").strip().lower().lstrip("@") == active_auth
                    and (m.get("message", "").strip() == active_msg or active_msg in m.get("message", "").strip() or m.get("message", "").strip() in active_msg)
                )
            ]
            candidate_msgs = scrolling_msgs
        else:
            candidate_msgs = display_msgs

        available_height = max_content_y - y_offset

        # Pre-measure candidate messages backwards from newest (bottom) to oldest (top)
        # to guarantee that newest incoming comments & active questions are ALWAYS rendered at the bottom!
        prepared_chats = []
        accumulated_h = 0

        for item in reversed(candidate_msgs):
            is_sc = item.get("is_superchat", False)
            is_cast = item.get("is_cast", False) or item.get("author_type") == "cast"
            raw_author = item.get("author", "Viewer").strip().lstrip("@")
            clean_author = f"@{raw_author.replace(' ', '')}"
            msg = item.get("message", "").strip()
            amount = item.get("amount", "")

            # Check if this item is the active question currently in-feed
            is_active_row = bool(
                has_active_question
                and not is_pinned_at_top
                and raw_author.lower() == active_auth
                and (msg == active_msg or active_msg in msg or msg in active_msg)
            )

            # Text wrapping
            max_text_w = card_w - (pad_x * 2 + (24 if is_active_row else 10))
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

            display_lines = wrapped_lines[:2] if wrapped_lines else [""]
            item_h = auth_h + len(display_lines) * line_h + (8 if self.is_vertical else 4)
            gap = 12 if self.is_vertical else 10

            needed_h = item_h + (gap if prepared_chats else 0)
            if accumulated_h + needed_h > available_height and prepared_chats:
                # Can't fit more older items above; preserve newest items at bottom
                break

            accumulated_h += needed_h
            prepared_chats.append({
                "item": item,
                "is_sc": is_sc,
                "is_cast": is_cast,
                "raw_author": raw_author,
                "clean_author": clean_author,
                "msg": msg,
                "amount": amount,
                "is_active_row": is_active_row,
                "display_lines": display_lines,
                "item_h": item_h,
                "gap": gap,
            })

        # Restore chronological order (top to bottom)
        recent_chats = list(reversed(prepared_chats))

        if not recent_chats and not is_pinned_at_top:
            empty_txt_sh = self._render_text(self.font_chat_msg, "(Waiting for live chat...)", (0, 0, 0))
            empty_txt = self._render_text(self.font_chat_msg, "(Waiting for live chat...)", (140, 165, 200))
            self.surf_chat_card.blit(empty_txt_sh, (pad_x + 1, y_offset + 1))
            self.surf_chat_card.blit(empty_txt, (pad_x, y_offset))
        else:
            for p_item in recent_chats:
                is_sc = p_item["is_sc"]
                is_cast = p_item["is_cast"]
                clean_author = p_item["clean_author"]
                amount = p_item["amount"]
                is_active_row = p_item["is_active_row"]
                display_lines = p_item["display_lines"]
                item_h = p_item["item_h"]

                sc_badge_str = f" [{amount}]" if is_sc else ""

                if is_sc:
                    author_color = (255, 215, 0)
                    msg_color = (255, 252, 245)
                    row_border_col = (255, 215, 0)
                elif is_cast:
                    author_color = (215, 140, 255)
                    msg_color = (245, 238, 255)
                    row_border_col = (215, 140, 255)
                else:
                    author_color = (0, 235, 255)
                    msg_color = (255, 255, 255)
                    row_border_col = (0, 240, 255)

                # ----------------------------------------------------------
                # IN-FEED ACTIVE ROW HIGHLIGHT (Soft glowing background fade, no border)
                # ----------------------------------------------------------
                if is_active_row and self.pinned_chat_alpha > 0.005:
                    row_w = card_w - (pad_x * 2) + 12
                    row_alpha = self.pinned_chat_alpha
                    bg_x = pad_x - 6
                    bg_y = y_offset - 4
                    bg_h = item_h + 8

                    bg_surf = pygame.Surface((row_w, bg_h), pygame.SRCALPHA)
                    # Soft ethereal glassmorphic glow behind text
                    pygame.draw.rect(bg_surf, (14, 26, 52, int(150 * row_alpha)), (0, 0, row_w, bg_h), border_radius=8)
                    pygame.draw.rect(bg_surf, (*row_border_col, int(35 * row_alpha)), (0, 0, row_w, bg_h), border_radius=8)
                    self.surf_chat_card.blit(bg_surf, (bg_x, bg_y))

                # Standard & Active text rendering at exact same fixed coordinates
                auth_str = f"{clean_author}{sc_badge_str}:"
                auth_sh = self._render_text(self.font_chat_author, auth_str, (0, 0, 0))
                self.surf_chat_card.blit(auth_sh, (pad_x + sh_off, y_offset + sh_off))
                auth_rend = self._render_text(self.font_chat_author, auth_str, author_color)
                self.surf_chat_card.blit(auth_rend, (pad_x, y_offset))

                if is_cast:
                    auth_w = self.font_chat_author.size(auth_str)[0]
                    badge_y = y_offset + max(0, (auth_h - (self.font_callout_tag.get_height() + (4 if self.is_vertical else 2))) // 2)
                    self._draw_cast_badge(self.surf_chat_card, pad_x + auth_w + 8, badge_y, alpha=1.0)

                msg_start_y = y_offset + auth_h - (2 if self.is_vertical else 0)
                for line_idx, line_text in enumerate(display_lines):
                    line_y = msg_start_y + line_idx * line_h
                    line_sh = self._render_text(self.font_chat_msg, line_text, (0, 0, 0))
                    self.surf_chat_card.blit(line_sh, (pad_x + sh_off, line_y + sh_off))
                    line_rend = self._render_text(self.font_chat_msg, line_text, msg_color)
                    self.surf_chat_card.blit(line_rend, (pad_x, line_y))

                y_offset += item_h + (12 if self.is_vertical else 10)

        self.screen.blit(self.surf_chat_card, (card_x, card_y))

    def _draw_ai_subtitle_card(
        self,
        is_speaking: bool,
        concurrent_viewers: int = 0,
        pinned_chat_message: Optional[Dict] = None,
    ):
        """
        Draws AI Co-Host streaming response center comment area:
        - When responding to a chat message and waiting for speech generation:
          Immediately displays the chat question formatted visually as it appears in the chat panel.
        - When the Oracle begins speaking:
          Smoothly transitions to displaying the Oracle's spoken statement in the mood color.
        - Resting/Idle:
          Displays the subtle motto or dissolved empty state.
        """
        if self.is_vertical:
            card_w, card_h = 940, 380
            card_x, card_y = (self.width - card_w) // 2, 749
        else:
            card_w, card_h = 880, 360
            card_x = self.core_cx - (card_w // 2)
            card_y = self.core_cy + 245

        self.surf_subtitle_card.fill((0, 0, 0, 0))

        # 1. Track active question arrival and reading linger duration
        dt = 1.0 / self.fps
        if pinned_chat_message and isinstance(pinned_chat_message, dict):
            curr_q_msg = pinned_chat_message.get("message", "").strip()
            if curr_q_msg and (curr_q_msg != self.active_question_text or self.question_fade_state == "idle") and curr_q_msg != self.last_completed_question_text:
                self.active_question_text = curr_q_msg
                self.active_question_author = pinned_chat_message.get("author", "Viewer").strip().lstrip("@")
                self.active_question_is_sc = pinned_chat_message.get("is_superchat", False)
                self.active_question_is_cast = (pinned_chat_message.get("is_cast", False) or pinned_chat_message.get("author_type") == "cast")
                self.active_question_amount = pinned_chat_message.get("amount", "")
                if self.ai_text_current and self.ai_text_alpha > 0.005:
                    self.ai_text_state = "fade_out"
                    self.ai_text_target = ""
                    self.subtitle_target_text = ""
                    self.question_fade_alpha = 0.0
                    self.question_fade_timer = 0.0
                    self.question_fade_state = "waiting_for_dissolve"
                else:
                    self.active_question_start_time = time.time()
                    self.question_fade_alpha = 0.0
                    self.question_fade_timer = 0.0
                    self.question_fade_state = "fade_in"
                    self.question_y_drift = 6.0
                    self.ai_text_current = ""
                    self.ai_text_target = ""
                    self.ai_text_alpha = 0.0
                    self.ai_text_state = "idle_empty"
        else:
            if self.question_fade_state in ("fade_in", "steady"):
                self.question_fade_state = "fade_out"
                self.question_fade_timer = 0.0
            elif self.question_fade_state == "idle":
                if self.active_question_text:
                    self.last_completed_question_text = self.active_question_text
                    self.active_question_text = ""
                    self.active_question_author = ""
                    self.active_question_is_sc = False
                    self.active_question_is_cast = False
                    self.active_question_amount = ""
                self.active_question_start_time = 0.0

        # 2. Timing Parameters & Calculations
        q_fade_in_sec = max(0.05, self.cfg.question_fade_in_sec)
        q_fade_out_sec = max(0.05, self.cfg.question_fade_out_sec)
        min_display_sec = max(0.1, self.cfg.question_min_display_sec)
        word_rate_sec = max(0.01, self.cfg.question_read_word_rate_sec)

        q_words = len(self.active_question_text.split()) if self.active_question_text else 0
        display_duration = max(min_display_sec, q_words * word_rate_sec)

        comment_fade_in_sec = max(0.05, self.cfg.comment_fade_in_sec)
        comment_fade_out_sec = max(0.05, self.cfg.comment_fade_out_sec)
        motto_pre_fade_in_sec = max(0.0, self.cfg.motto_pre_fade_in_sec)
        motto_fade_in_sec = max(0.05, self.cfg.motto_fade_in_sec)
        motto_fade_out_sec = max(0.05, self.cfg.motto_fade_out_sec)

        comment_fade_in_rate = 1.0 / comment_fade_in_sec
        comment_fade_out_rate = 1.0 / comment_fade_out_sec
        motto_fade_in_rate = 1.0 / motto_fade_in_sec
        motto_fade_out_rate = 1.0 / motto_fade_out_sec

        # 3. Discrete Phase Execution: fade_in -> steady display hold -> fade_out -> idle
        if self.question_fade_state == "fade_in":
            self.question_fade_timer += dt
            prog = min(1.0, self.question_fade_timer / q_fade_in_sec)
            self.question_fade_alpha = prog
            self.question_y_drift = 6.0 * (1.0 - prog)
            if prog >= 1.0:
                self.question_fade_alpha = 1.0
                self.question_y_drift = 0.0
                self.question_fade_timer = 0.0
                self.question_fade_state = "steady"

        elif self.question_fade_state == "steady":
            self.question_fade_timer += dt
            self.question_fade_alpha = 1.0
            self.question_y_drift = 0.0
            if not pinned_chat_message:
                self.question_fade_state = "fade_out"
                self.question_fade_timer = 0.0

        elif self.question_fade_state == "fade_out":
            self.question_fade_timer += dt
            prog = min(1.0, self.question_fade_timer / q_fade_out_sec)
            self.question_fade_alpha = max(0.0, 1.0 - prog)
            self.question_y_drift = -4.0 * prog
            if prog >= 1.0:
                self.question_fade_alpha = 0.0
                self.question_fade_timer = 0.0
                self.question_fade_state = "idle"
                self.question_y_drift = 0.0
                if self.active_question_text:
                    self.last_completed_question_text = self.active_question_text
                    self.active_question_text = ""
                    self.active_question_author = ""
                    self.active_question_is_sc = False
                    self.active_question_is_cast = False
                    self.active_question_amount = ""

        showing_question_preview = bool(
            self.active_question_text
            and self.question_fade_state in ("fade_in", "steady", "fade_out")
            and self.question_fade_alpha > 0.005
        )

        if showing_question_preview:
            # ------------------------------------------------------------------
            # QUESTION PREVIEW: Display question formatted visually like chat
            # ------------------------------------------------------------------
            if pinned_chat_message and isinstance(pinned_chat_message, dict):
                raw_author = pinned_chat_message.get("author", self.active_question_author or "Viewer").strip().lstrip("@")
                is_sc = pinned_chat_message.get("is_superchat", self.active_question_is_sc)
                is_cast = (pinned_chat_message.get("is_cast", False) or pinned_chat_message.get("author_type") == "cast") or self.active_question_is_cast
                amount = pinned_chat_message.get("amount", self.active_question_amount)
                msg = self.active_question_text or pinned_chat_message.get("message", "").strip()
            else:
                raw_author = self.active_question_author or "Viewer"
                is_sc = self.active_question_is_sc
                is_cast = self.active_question_is_cast
                amount = self.active_question_amount
                msg = self.active_question_text

            clean_author = f"@{raw_author.replace(' ', '')}"
            sc_badge_str = f" [{amount}]" if is_sc else ""

            if is_sc:
                author_color = (255, 215, 0)
            elif is_cast:
                author_color = (215, 140, 255)
            else:
                author_color = (0, 235, 255)

            pad_x = 48 if self.is_vertical else 42
            max_text_w = card_w - (pad_x * 2)

            # Wrap question text
            words = msg.split(" ")
            wrapped_lines = []
            cur_l = ""
            for w in words:
                test_l = f"{cur_l} {w}".strip()
                if self.font_ai_subtitle.size(test_l)[0] < max_text_w:
                    cur_l = test_l
                else:
                    if cur_l:
                        wrapped_lines.append(cur_l)
                    cur_l = w
            if cur_l:
                wrapped_lines.append(cur_l)

            display_lines = wrapped_lines[:4] if wrapped_lines else [""]
            line_h = 44 if self.is_vertical else 40
            auth_h = 36 if self.is_vertical else 32
            total_content_h = auth_h + (len(display_lines) * line_h) + 8

            if total_content_h < card_h:
                y_start = (card_h - total_content_h) // 2
            else:
                y_start = 14
            y_start += self.question_y_drift

            alpha_int = int(np.clip(self.question_fade_alpha * 255, 0, 255))

            # 1. Author Header line (Centered horizontally)
            auth_str = f"{clean_author}{sc_badge_str}:"
            auth_w = self.font_chat_author.size(auth_str)[0]
            sh_off = 2 if self.is_vertical else 1

            if is_cast:
                badge_label = self.cfg.cast_badge_label
                badge_sample_txt = self._render_text(self.font_callout_tag, f"{badge_label}", (240, 185, 255))
                pad_w = 6 if self.is_vertical else 5
                badge_w = badge_sample_txt.get_width() + (pad_w * 2)
                total_auth_w = auth_w + 8 + badge_w
                auth_x = (card_w - total_auth_w) // 2
                badge_x = auth_x + auth_w + 8
                badge_y = y_start + max(0, (auth_h - (self.font_callout_tag.get_height() + (4 if self.is_vertical else 2))) // 2)
            else:
                auth_x = (card_w - auth_w) // 2
                badge_x = 0
                badge_y = 0

            auth_sh = self._render_text(self.font_chat_author, auth_str, (0, 0, 0))
            self.surf_ai_text.fill((0, 0, 0, 0))
            self.surf_ai_text.blit(auth_sh, (auth_x + sh_off, y_start + sh_off))
            auth_rend = self._render_text(self.font_chat_author, auth_str, author_color)
            self.surf_ai_text.blit(auth_rend, (auth_x, y_start))

            if is_cast:
                self._draw_cast_badge(self.surf_ai_text, badge_x, badge_y, alpha=self.question_fade_alpha)

            # 2. Message lines (Centered horizontally)
            msg_y_start = y_start + auth_h + 4
            for idx, line_txt in enumerate(display_lines):
                line_w = self.font_ai_subtitle.size(line_txt)[0]
                line_x = (card_w - line_w) // 2
                line_y = msg_y_start + idx * line_h

                line_sh = self._render_text(self.font_ai_subtitle, line_txt, (0, 0, 0))
                self.surf_ai_text.blit(line_sh, (line_x + sh_off, line_y + sh_off))
                line_rend = self._render_text(self.font_ai_subtitle, line_txt, (255, 255, 255))
                self.surf_ai_text.blit(line_rend, (line_x, line_y))

            self.surf_ai_text.set_alpha(alpha_int)
            self.surf_subtitle_card.blit(self.surf_ai_text, (0, 0))
            self.screen.blit(self.surf_subtitle_card, (card_x, card_y))
            return

        # ----------------------------------------------------------------------
        # ORACLE SPOKEN STATEMENT / IDLE MOTTO MANIFESTATION
        # ----------------------------------------------------------------------
        motto = self.cfg.motto_phrase
        if self.cfg.vox_only_mode and is_speaking:
            desired_target = ""
        elif self.subtitle_target_text:
            desired_target = self.subtitle_target_text
        elif self.ai_text_state in ("idle_empty", "fade_out") and self.ai_text_target == "":
            desired_target = ""
        else:
            desired_target = motto

        # State Machine: Ethereal Emergence from Nowhere and Dissolution into Nowhere
        if desired_target != self.ai_text_target or (self.ai_text_current != desired_target and self.ai_text_state not in ("fade_out", "fade_in", "motto_pause", "idle_empty")):
            self.ai_text_target = desired_target
            # If current statement is visible and different from desired target, fade it out first!
            if self.ai_text_current and self.ai_text_current != desired_target and self.ai_text_alpha > 0.005:
                self.ai_text_state = "fade_out"
            elif desired_target:
                if desired_target == motto:
                    self.ai_text_current = ""
                    self.ai_text_alpha = 0.0
                    if motto_pre_fade_in_sec > 0.0:
                        self.ai_text_state = "motto_pause"
                        self.motto_pause_timer = motto_pre_fade_in_sec
                    else:
                        self.ai_text_current = motto
                        self.ai_text_state = "fade_in"
                        self.ai_text_y_drift = 6.0
                else:
                    self.ai_text_current = desired_target
                    self.ai_text_alpha = 0.0
                    self.ai_text_state = "fade_in"
                    self.ai_text_y_drift = 6.0
            else:
                self.ai_text_current = ""
                self.ai_text_alpha = 0.0
                self.ai_text_state = "idle_empty"

        dt = 1.0 / self.fps
        if self.ai_text_state == "fade_out":
            out_rate = motto_fade_out_rate if self.ai_text_current == motto else comment_fade_out_rate
            self.ai_text_alpha -= dt * out_rate
            self.ai_text_y_drift = -4.0 * (1.0 - max(0.0, self.ai_text_alpha))
            if self.ai_text_alpha <= 0.0:
                self.ai_text_alpha = 0.0
                self.ai_text_y_drift = 6.0
                if self.question_fade_state == "waiting_for_dissolve":
                    self.ai_text_current = ""
                    self.ai_text_target = ""
                    self.ai_text_state = "idle_empty"
                    self.question_fade_state = "fade_in"
                    self.question_fade_timer = 0.0
                    self.question_fade_alpha = 0.0
                    self.question_y_drift = 6.0
                    self.active_question_start_time = time.time()
                elif self.ai_text_target == motto:
                    self.ai_text_current = ""
                    if motto_pre_fade_in_sec > 0.0:
                        self.ai_text_state = "motto_pause"
                        self.motto_pause_timer = motto_pre_fade_in_sec
                    else:
                        self.ai_text_current = motto
                        self.ai_text_alpha = 0.0
                        self.ai_text_state = "fade_in"
                        self.ai_text_y_drift = 6.0
                elif self.ai_text_target:
                    self.ai_text_current = self.ai_text_target
                    self.ai_text_alpha = 0.0
                    self.ai_text_state = "fade_in"
                    self.ai_text_y_drift = 6.0
                else:
                    self.ai_text_current = ""
                    self.ai_text_state = "idle_empty"

        elif self.ai_text_state == "motto_pause":
            self.ai_text_alpha = 0.0
            self.ai_text_y_drift = 0.0
            self.motto_pause_timer -= dt
            if self.motto_pause_timer <= 0.0:
                self.ai_text_current = motto
                self.ai_text_alpha = 0.0
                self.ai_text_state = "fade_in"
                self.ai_text_y_drift = 6.0

        elif self.ai_text_state == "fade_in":
            in_rate = motto_fade_in_rate if self.ai_text_current == motto else comment_fade_in_rate
            self.ai_text_alpha += dt * in_rate
            self.ai_text_y_drift = 6.0 * (1.0 - min(1.0, self.ai_text_alpha))
            if self.ai_text_alpha >= 1.0:
                self.ai_text_alpha = 1.0
                self.ai_text_y_drift = 0.0
                self.ai_text_state = "steady"

        elif self.ai_text_state == "steady":
            self.ai_text_alpha = 1.0
            self.ai_text_y_drift = 0.0

        elif self.ai_text_state == "idle_empty":
            self.ai_text_alpha = 0.0
            self.ai_text_y_drift = 0.0

        # Maintain typewriter_index for compatibility with callers
        if self.ai_text_current:
            self.typewriter_index = len(self.ai_text_current)

        # Render Ethereal Floating Text Centered Horizontally & Vertically
        self.surf_ai_text.fill((0, 0, 0, 0))

        if self.ai_text_alpha > 0.005 and self.ai_text_current:
            pad_x = 52 if self.is_vertical else 48
            max_text_w = card_w - (pad_x * 2)

            words = self.ai_text_current.split(" ")
            lines = []
            cur_line = ""
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

            display_lines = lines[:7]
            line_h = 46 if self.is_vertical else 42
            total_text_h = len(display_lines) * line_h

            # Center vertically within the comment container
            if total_text_h < card_h:
                y_start = (card_h - total_text_h) // 2
            else:
                y_start = 12
            y_start += self.ai_text_y_drift

            # Dynamic mood-matched color (for motto, use steady celestial color so it never flashes or shifts color on mood changes)
            if self.ai_text_current == motto:
                mood_color = (0, 200, 255)
            else:
                mood_color = tuple(int(np.clip(c, 0, 255)) for c in self.c_primary)

            alpha_int = int(np.clip(self.ai_text_alpha * 255, 0, 255))
            for i, line in enumerate(display_lines):
                cur_y = int(y_start + i * line_h)
                line_w = self.font_ai_subtitle.size(line)[0]
                line_x = (card_w - line_w) // 2

                # Crisp dark drop shadow for sharp edge contrast
                line_sh = self._render_text(self.font_ai_subtitle, line, (0, 0, 0))
                self.surf_ai_text.blit(line_sh, (line_x + 2, cur_y + 2))

                # Mood-matched vibrant text
                line_rend = self._render_text(self.font_ai_subtitle, line, mood_color)
                self.surf_ai_text.blit(line_rend, (line_x, cur_y))

            self.surf_ai_text.set_alpha(alpha_int)
            self.surf_subtitle_card.blit(self.surf_ai_text, (0, 0))

        self.screen.blit(self.surf_subtitle_card, (card_x, card_y))

    # --------------------------------------------------------------------------
    # Promotional Callout Graphic Overlays ("Ask God" & "Like & Subscribe")
    # --------------------------------------------------------------------------
    @property
    def is_promo_active(self) -> bool:
        """Returns True if a promotional overlay is currently entering, displaying, or exiting."""
        return self.promo_state in ("entrance", "display") or (self.promo_state == "exit" and self.promo_alpha > 0.05)

    def _update_promo_state(self, dt: float, is_speaking: bool = False, is_turn_busy: bool = False):
        """Updates animation timers, easing curves, and state transitions for promotional callout overlays."""
        entrance_duration = max(0.2, self.cfg.promo_overlay_entrance_sec)
        exit_duration = max(0.2, self.cfg.promo_overlay_exit_sec)

        # If turn is busy (avatar speaking, question displayed/generating), hold promo in off state
        if is_speaking or is_turn_busy:
            if self.promo_state in ("entrance", "display"):
                self.promo_state = "exit"
                self.promo_state_timer = 0.0
                self.promo_slide_factor = 0.0
            elif self.promo_state == "off":
                self.promo_timer = max(self.promo_timer, 8.0)

        if self.promo_state == "off":
            if self.promo_enabled and self.promo_mode == "timer" and not (is_speaking or is_turn_busy):
                self.promo_timer -= dt
                if self.promo_timer <= 0:
                    self.promo_state = "entrance"
                    self.promo_state_timer = 0.0
                    self.promo_slide_factor = 0.0
                    self.promo_alpha = 0.0
        elif self.promo_state == "entrance":
            self.promo_state_timer += dt
            prog = min(1.0, self.promo_state_timer / entrance_duration)
            # Quartic ease-out for a silky, cushioned landing
            ease_pos = 1.0 - (1.0 - prog) ** 4
            # Sine ease-out for luminous opacity bloom (promptly visible, settles gently)
            ease_alpha = math.sin(prog * (math.pi / 2.0))
            self.promo_slide_factor = ease_pos
            self.promo_alpha = ease_alpha
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
                self.promo_slide_factor = 0.0
        elif self.promo_state == "exit":
            self.promo_state_timer += dt
            prog = min(1.0, self.promo_state_timer / exit_duration)
            # Quintic SmootherStep (zero initial and final velocity for butter-smooth acceleration & deceleration)
            ease_drift = (prog ** 3) * (prog * (prog * 6.0 - 15.0) + 10.0)
            # Smooth Cosine fade: lingers legibly for first half of exit before softly dissolving into starlight
            ease_alpha = max(0.0, 0.5 * (1.0 + math.cos(prog * math.pi)))
            self.promo_slide_factor = ease_drift
            self.promo_alpha = ease_alpha
            if prog >= 1.0:
                self.promo_state = "off"
                self.promo_state_timer = 0.0
                self.promo_timer = self.promo_interval
                self.promo_slide_factor = 0.0
                self.promo_alpha = 0.0
                # Alternate to the other promo for next appearance in timer mode
                if self.promo_mode == "timer":
                    self.promo_current_type = "like_sub" if self.promo_current_type == "ask_god" else "ask_god"

    def _draw_promo_callout_overlay(self, dt: float, is_speaking: bool = False, is_turn_busy: bool = False):
        """Coordinates and renders the active promotional callout overlay card with smooth cinematic motion."""
        self._update_promo_state(dt, is_speaking=is_speaking, is_turn_busy=is_turn_busy)

        if self.promo_state == "off" or self.promo_alpha <= 0.005:
            return

        hover_amp = self.cfg.promo_overlay_hover_amp
        # Continuous harmonic hover oscillation (unbroken phase continuity across all state transitions)
        hover_y = math.sin(self.time_elapsed * 2.2) * hover_amp
        hover_x = math.cos(self.time_elapsed * 1.4) * (hover_amp * 0.35)

        # Calculate snug card width tailored dynamically to contained text and badges
        pad_x = 34 if self.is_vertical else 28
        if self.promo_current_type == "ask_god":
            sub_str = "You already know the answer but I enjoy the theater"
            title_str = "Ask Anything"
            badge_r = 19 if self.is_vertical else 16
            badge_w = (badge_r * 2 + 8) + 14
        else:
            sub_str = "It is, however, appreciated • Ring bell for live alerts"
            title_str = "Subscribing Changes Nothing."
            pill_w = 48 if self.is_vertical else 40
            badge_w = pill_w + (16 if self.is_vertical else 12) + 14

        title_w = self.font_callout_title.size(title_str)[0]
        sub_w = self.font_callout_sub.size(sub_str)[0]
        content_w = max(sub_w, badge_w + title_w)
        card_w = content_w + (pad_x * 2)
        card_h = 126 if self.is_vertical else 110

        if self.is_vertical:
            target_x = (self.width - card_w) // 2
            target_y = self.core_cy - (card_h // 2)

            if self.promo_state == "entrance":
                cur_x = round(target_x + hover_x * self.promo_slide_factor)
                cur_y = round(target_y + 45.0 * (1.0 - self.promo_slide_factor) + hover_y * self.promo_slide_factor)
            elif self.promo_state == "display":
                cur_x = round(target_x + hover_x)
                cur_y = round(target_y + hover_y)
            else:  # exit: gentle upward ethereal ascension with smooth hover decay
                cur_x = round(target_x + hover_x * (1.0 - self.promo_slide_factor))
                cur_y = round(target_y - 24.0 * self.promo_slide_factor + hover_y * (1.0 - self.promo_slide_factor))
        else:
            target_x = (self.width - card_w) // 2
            target_y = self.core_cy - (card_h // 2)

            if self.promo_state == "entrance":
                # Glide in from left (-260px) with subtle upward settling arc
                cur_x = round(target_x - 260.0 * (1.0 - self.promo_slide_factor) + hover_x * self.promo_slide_factor)
                cur_y = round(target_y + 14.0 * (1.0 - self.promo_slide_factor) + hover_y * self.promo_slide_factor)
            elif self.promo_state == "display":
                cur_x = round(target_x + hover_x)
                cur_y = round(target_y + hover_y)
            else:  # exit: gentle drift in reading flow direction + upward ethereal float with smooth hover decay
                cur_x = round(target_x + 28.0 * self.promo_slide_factor + hover_x * (1.0 - self.promo_slide_factor))
                cur_y = round(target_y - 18.0 * self.promo_slide_factor + hover_y * (1.0 - self.promo_slide_factor))

        self.surf_promo_card.fill((0, 0, 0, 0))

        if self.promo_current_type == "ask_god":
            self._draw_ask_god_card(self.surf_promo_card, card_w, card_h, self.time_elapsed)
        else:
            self._draw_like_sub_card(self.surf_promo_card, card_w, card_h, self.time_elapsed)

        # Apply whole-card alpha modulation (smoothly fades frame, text, badges, and specular glints in perfect unison)
        alpha_byte = max(0, min(255, int(self.promo_alpha * 255)))
        self.surf_promo_card.set_alpha(alpha_byte)

        # Blit the precisely sized card area onto screen
        card_subsurf = self.surf_promo_card.subsurface((0, 0, card_w, card_h))
        self.screen.blit(card_subsurf, (cur_x, cur_y))

    def _draw_ask_god_card(self, surf: pygame.Surface, w: int, h: int, t: float):
        """
        Draws the streamlined 'Ask Anything' inquiry callout card:
        - Deep space sapphire glassmorphic container with radiant gold/cyan border
        - Centered title row with celestial sunbeam question glyph + bold title
        - Centered high-legibility subtitle
        - Shimmering specular rim sweep & corner glints
        """
        # 1. Glassmorphism Card Frame
        bg_alpha = 255 if self.is_vertical else 248
        pygame.draw.rect(surf, (10, 16, 32, bg_alpha), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(surf, (20, 36, 68, 235), (2, 2, w - 4, h - 4), border_radius=14)

        # Radiant Golden/Cyan Border Glow
        border_pulse = 0.85 + 0.15 * math.sin(t * 5.0)
        gold_border = (255, 215, 0)
        pygame.draw.rect(surf, (*gold_border, min(255, int(210 * border_pulse))), (0, 0, w, h), width=2, border_radius=16)

        # Top rim specular sheen
        pygame.draw.line(surf, (255, 255, 255, 175), (24, 2), (w - 24, 2), 1)

        # 2. Centered Title Row: Celestial Question Badge + Title (Centered Lockup)
        title_str = "Ask Anything"
        title_rend = self._render_text(self.font_callout_title, title_str, (255, 250, 230))
        sh_rend = self._render_text(self.font_callout_title, title_str, (180, 140, 20))

        badge_r = 19 if self.is_vertical else 16
        lockup_gap = 14
        total_title_w = (badge_r * 2 + 8) + lockup_gap + title_rend.get_width()
        lockup_x = (w - total_title_w) // 2
        badge_cx = lockup_x + badge_r + 4
        badge_cy = 44 if self.is_vertical else 38
        title_x = lockup_x + (badge_r * 2 + 8) + lockup_gap
        title_y = 26 if self.is_vertical else 22

        # Rotating halo rays around question badge
        ray_angle_base = t * 1.6
        for i in range(8):
            ang = ray_angle_base + i * (math.pi / 4.0)
            r_in = badge_r + 2
            r_out = badge_r + 7 + 3.0 * math.sin(t * 6.0 + i)
            p1 = (int(badge_cx + r_in * math.cos(ang)), int(badge_cy + r_in * math.sin(ang)))
            p2 = (int(badge_cx + r_out * math.cos(ang)), int(badge_cy + r_out * math.sin(ang)))
            pygame.draw.line(surf, (255, 215, 0, 180), p1, p2, 2)

        # Core Badge Circle
        pygame.draw.circle(surf, (20, 36, 68, 240), (badge_cx, badge_cy), badge_r)
        pygame.draw.circle(surf, (255, 215, 0, 235), (badge_cx, badge_cy), badge_r, 2)
        pygame.draw.circle(surf, (0, 240, 255, 140), (badge_cx, badge_cy), badge_r - 4, 1)

        # White Question Mark Glyph
        q_rend = self._render_text(self.font_callout_icon, "?", (255, 255, 255))
        surf.blit(q_rend, (badge_cx - q_rend.get_width() // 2, badge_cy - q_rend.get_height() // 2 - 1))

        # Title Blit with shadow
        surf.blit(sh_rend, (title_x + 2, title_y + 2))
        surf.blit(title_rend, (title_x, title_y))

        # 3. Bottom Subtitle Row (Centered & fully visible)
        sub_str = "You already know the answer but I enjoy the theater"
        sub_rend = self._render_text(self.font_callout_sub, sub_str, (195, 225, 255))
        sub_w = sub_rend.get_width()
        sub_x = max(20, (w - sub_w) // 2)
        sub_y = 78 if self.is_vertical else 68
        sh_sub = self._render_text(self.font_callout_sub, sub_str, (0, 0, 0))
        surf.blit(sh_sub, (sub_x + 1, sub_y + 1))
        surf.blit(sub_rend, (sub_x, sub_y))

        # 4. Specular Rim Sheen Light Sweep
        shimmer_pos = int((t * 280) % (w + 140)) - 70
        if 0 <= shimmer_pos < w:
            s_left = max(10, shimmer_pos - 35)
            s_right = min(w - 10, shimmer_pos + 35)
            pygame.draw.line(surf, (255, 255, 255, 220), (s_left, 1), (s_right, 1), 2)
            pygame.draw.line(surf, (255, 215, 0, 180), (s_left, h - 2), (s_right, h - 2), 2)

        # 5. Corner Sparkle Glints
        sp_a = min(255, int(140 + 115 * math.sin(t * 8.0)))
        for sp_pos in [(w - 18, 18), (w - 28, h - 18)]:
            sx, sy = sp_pos
            pygame.draw.circle(surf, (255, 255, 255, sp_a), (sx, sy), 2)
            pygame.draw.line(surf, (255, 215, 0, sp_a), (sx - 6, sy), (sx + 6, sy), 1)
            pygame.draw.line(surf, (255, 215, 0, sp_a), (sx, sy - 6), (sx, sy + 6), 1)

    def _draw_like_sub_card(self, surf: pygame.Surface, w: int, h: int, t: float):
        """
        Draws the streamlined 'Subscribing Changes Nothing' community callout card:
        - Sleek ruby-tinted glassmorphic container with neon coral/magenta border
        - Centered title row with YouTube Play badge + harmonic ringing bell + bold title
        - Centered high-legibility subtitle
        - Shimmering specular rim sweep & corner glints
        """
        # 1. Glassmorphism Card Frame
        bg_alpha = 255 if self.is_vertical else 248
        pygame.draw.rect(surf, (24, 10, 20, bg_alpha), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(surf, (48, 16, 34, 235), (2, 2, w - 4, h - 4), border_radius=14)

        # Radiant Neon Coral/Ruby Border Glow
        border_pulse = 0.85 + 0.15 * math.sin(t * 5.0)
        coral_border = (255, 50, 90)
        pygame.draw.rect(surf, (*coral_border, min(255, int(210 * border_pulse))), (0, 0, w, h), width=2, border_radius=16)

        # Top rim specular sheen
        pygame.draw.line(surf, (255, 220, 230, 175), (24, 2), (w - 24, 2), 1)

        # 2. Centered Title Row: YouTube & Bell Badge + Title (Centered Lockup)
        title_str = "Subscribing Changes Nothing."
        title_rend = self._render_text(self.font_callout_title, title_str, (255, 245, 245))
        sh_rend = self._render_text(self.font_callout_title, title_str, (160, 20, 50))

        pill_w, pill_h = (48, 30) if self.is_vertical else (40, 26)
        badge_area_w = pill_w + (16 if self.is_vertical else 12)
        lockup_gap = 14
        total_title_w = badge_area_w + lockup_gap + title_rend.get_width()
        lockup_x = (w - total_title_w) // 2

        # YouTube Red Squircle Pill
        pill_x = lockup_x
        pill_y = 28 if self.is_vertical else 24
        pygame.draw.rect(surf, (255, 20, 50, 240), (pill_x, pill_y, pill_w, pill_h), border_radius=8)
        pygame.draw.rect(surf, (255, 255, 255, 190), (pill_x, pill_y, pill_w, pill_h), width=1, border_radius=8)

        # White play triangle inside pill
        if self.is_vertical:
            tri_pts = [
                (pill_x + 18, pill_y + 8),
                (pill_x + 18, pill_y + 22),
                (pill_x + 33, pill_y + 15),
            ]
        else:
            tri_pts = [
                (pill_x + 15, pill_y + 7),
                (pill_x + 15, pill_y + 19),
                (pill_x + 28, pill_y + 13),
            ]
        pygame.draw.polygon(surf, (255, 255, 255, 250), tri_pts)

        # Harmonically Swaying Notification Bell badge overlapping lower right
        bell_cx = pill_x + pill_w - 2
        bell_cy = pill_y + pill_h - 2
        swing = math.sin(t * 3.5)
        clapper_x = int(bell_cx + swing * 2.0)
        bell_r = 14 if self.is_vertical else 12

        # Bell pill background
        pygame.draw.circle(surf, (35, 15, 25, 240), (bell_cx, bell_cy), bell_r)
        pygame.draw.circle(surf, (255, 200, 50, 230), (bell_cx, bell_cy), bell_r, 1)

        # Bell Dome
        dome_w = 7 if self.is_vertical else 5
        dome_h = 6 if self.is_vertical else 4
        bell_pts = [
            (bell_cx - dome_w, bell_cy + 3),
            (bell_cx - 3, bell_cy - dome_h),
            (bell_cx + 3, bell_cy - dome_h),
            (bell_cx + dome_w, bell_cy + 3),
        ]
        pygame.draw.polygon(surf, (255, 215, 0, 245), bell_pts)
        pygame.draw.circle(surf, (255, 240, 120, 250), (clapper_x, bell_cy + 5), 2)

        # Smooth radiating golden sound ripples around bell (continuous alpha without popping)
        ring_phase = (t * 2.8) % 1.0
        ring_r = int(bell_r + ring_phase * 6.0)
        ring_alpha = max(0, int((1.0 - ring_phase) * 150 * (0.5 + 0.5 * abs(swing))))
        if ring_alpha > 5:
            pygame.draw.circle(surf, (255, 200, 50, ring_alpha), (bell_cx, bell_cy), ring_r, 1)

        # Title Blit
        title_x = lockup_x + badge_area_w + lockup_gap
        title_y = 26 if self.is_vertical else 22
        surf.blit(sh_rend, (title_x + 2, title_y + 2))
        surf.blit(title_rend, (title_x, title_y))

        # 3. Bottom Subtitle Row (Centered & fully visible)
        sub_str = "It is, however, appreciated • Ring bell for live alerts"
        sub_rend = self._render_text(self.font_callout_sub, sub_str, (255, 220, 205))
        sub_w = sub_rend.get_width()
        sub_x = max(20, (w - sub_w) // 2)
        sub_y = 78 if self.is_vertical else 68
        sh_sub = self._render_text(self.font_callout_sub, sub_str, (0, 0, 0))
        surf.blit(sh_sub, (sub_x + 1, sub_y + 1))
        surf.blit(sub_rend, (sub_x, sub_y))

        # 4. Specular Rim Sheen Light Sweep
        shimmer_pos = int((t * 280) % (w + 140)) - 70
        if 0 <= shimmer_pos < w:
            s_left = max(10, shimmer_pos - 35)
            s_right = min(w - 10, shimmer_pos + 35)
            pygame.draw.line(surf, (255, 255, 255, 220), (s_left, 1), (s_right, 1), 2)
            pygame.draw.line(surf, (255, 60, 120, 190), (s_left, h - 2), (s_right, h - 2), 2)

        # 5. Corner Sparkle Glints
        sp_a = min(255, int(140 + 115 * math.sin(t * 8.0)))
        for sp_pos in [(w - 18, 18), (w - 28, h - 18)]:
            sx, sy = sp_pos
            pygame.draw.circle(surf, (255, 255, 255, sp_a), (sx, sy), 2)
            pygame.draw.line(surf, (255, 60, 120, sp_a), (sx - 6, sy), (sx + 6, sy), 1)
            pygame.draw.line(surf, (255, 60, 120, sp_a), (sx, sy - 6), (sx, sy + 6), 1)

    def set_utterance_state(self, is_open: bool):
        """No-op on direct visualizer (state is tracked in shared memory by VisualizerProxy)."""
        pass

    def close(self):
        """Closes Pygame display window and releases SDL hardware surfaces."""
        try:
            pygame.display.quit()
            pygame.quit()
        except Exception:
            pass


