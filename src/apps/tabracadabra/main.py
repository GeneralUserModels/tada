#!/usr/bin/env python3
import os
import tempfile
import threading
import time
import base64
import io
import json
import logging
import re
import urllib.request
import urllib.error
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
import httpx
import litellm
from litellm import completion as litellm_completion
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter, before_sleep_log

logger = logging.getLogger(__name__)

import mss
from PIL import Image, ImageDraw

import Quartz

from connectors.screen.napsack.recorder import (
    DEFAULT_TARGET_DPI,
    TABRACADABRA_LATEST_FRAME_PNG,
)

load_dotenv()

# ------------- Constants -------------
JOINER = "\u2060"  # WORD JOINER (plays nice with Backspace)
SPINNER_FRAMES_HOLDING = ["◐", "◓", "◑", "◒"]
SPINNER_PROGRESS_DURATION_S = 9.0
SPINNER_TICK_INTERVAL_S = 0.12
# Give macOS a brief chance to apply posted backspaces before first content.
POST_SPINNER_DRAIN_S = 0.04

# Keycodes
KC_TAB = 48       # 0x30
KC_BACKSPACE = 51 # 0x33

# Tagging for our own events
OUR_EVENT_TAG = 0xC0DEFEED

# Zero-width chars for normalization
_ZW_CHARS = ("\u200B", "\u2060")

# Flag file to suppress screen connector aggregation during active streaming
_SUPPRESS_FLAG = os.path.join(tempfile.gettempdir(), "tada_tab_active")
_DEBUG_RENDER_DIR = os.path.join(tempfile.gettempdir(), "tada_tabracadabra_debug")
_DEBUG_RENDER_LATEST_PNG = os.path.join(_DEBUG_RENDER_DIR, "rendered_latest.png")


def load_prompt() -> str:
    """Load the tab prompt from the file next to this module."""
    prompt_path = Path(__file__).parent / "tab_prompt.txt"
    return prompt_path.read_text()


# ------------- Screenshot (napsack shared frame only; screen MCP writes TABRACADABRA_LATEST_FRAME_PNG) -------------
def capture_active_monitor_as_data_url(target_dpi=DEFAULT_TARGET_DPI):
    """PNG data URL from napsack's latest shared frame. DPI scaling was applied when the frame was captured."""
    del target_dpi  # unused; kept for call-site compatibility
    t0 = time.perf_counter()
    slow_ms = 500
    max_age = float(os.getenv("TABRACADABRA_FRAME_MAX_AGE_S", "5"))
    try:
        st = os.stat(TABRACADABRA_LATEST_FRAME_PNG)
    except OSError as e:
        raise RuntimeError(
            f"No shared frame at {TABRACADABRA_LATEST_FRAME_PNG}. "
            "Run Tada with the screen connector (MCP) so the recorder can publish frames."
        ) from e
    age_s = time.time() - st.st_mtime
    if age_s > max_age:
        raise RuntimeError(
            f"Shared frame is stale ({age_s:.1f}s old, max {max_age}s via TABRACADABRA_FRAME_MAX_AGE_S). "
            "Screen recorder may be stopped or stuck."
        )
    t1 = time.perf_counter()
    try:
        with Image.open(TABRACADABRA_LATEST_FRAME_PNG) as im:
            out_img = im.convert("RGB").copy()
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Could not read shared frame at {TABRACADABRA_LATEST_FRAME_PNG}") from e
    cursor_info = _annotate_with_cursor_dot(out_img)
    _save_debug_rendered_frame(out_img)
    t_load = time.perf_counter()
    buf = io.BytesIO()
    out_img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"
    t_end = time.perf_counter()
    total_ms = (t_end - t0) * 1000
    if total_ms >= slow_ms:
        file_ms = (t_load - t1) * 1000
        encode_ms = (t_end - t_load) * 1000
        print(
            f"[tabracadabra] timing screenshot_detail source=shared file_ms={file_ms:.1f} "
            f"encode_ms={encode_ms:.1f} total_ms={total_ms:.1f}",
            flush=True,
        )
    return data_url, cursor_info


def _save_debug_rendered_frame(image: Image.Image) -> None:
    """Persist latest rendered frame for local debugging."""
    try:
        os.makedirs(_DEBUG_RENDER_DIR, exist_ok=True)
        image.save(_DEBUG_RENDER_LATEST_PNG, format="PNG")
    except Exception as e:
        print(f"[tabracadabra] debug frame save failed: {e}", flush=True)


def _get_cursor_position() -> tuple[float, float] | None:
    """Return global cursor coordinates in CoreGraphics space (origin at bottom-left)."""
    try:
        ev = Quartz.CGEventCreate(None)
        if ev is None:
            return None
        loc = Quartz.CGEventGetLocation(ev)
        return float(loc.x), float(loc.y)
    except Exception:
        return None


def _annotate_with_cursor_dot(image: Image.Image) -> dict | None:
    """
    Draw a red dot where the cursor is and return metadata.
    Returns None when cursor location cannot be resolved.
    """
    pos = _get_cursor_position()
    if pos is None:
        return None

    x_global, y_global = pos
    width, height = image.size

    display_bounds = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    disp_x = float(display_bounds.origin.x)
    disp_y = float(display_bounds.origin.y)
    disp_w = float(display_bounds.size.width)
    disp_h = float(display_bounds.size.height)
    if disp_w <= 1 or disp_h <= 1:
        return None

    # Map global cursor coordinates into normalized display coordinates.
    rel_x = (x_global - disp_x) / disp_w
    rel_y = (y_global - disp_y) / disp_h

    # On macOS, CGEvent location is effectively top-left-oriented for this path.
    # Keep env override to flip if needed in unusual setups.
    flip_y = os.getenv("TABRACADABRA_CURSOR_FLIP_Y", "0") == "1"
    if flip_y:
        rel_y = 1.0 - rel_y

    x_img = int(round(rel_x * (width - 1)))
    y_img = int(round(rel_y * (height - 1)))

    inside = 0 <= x_img < width and 0 <= y_img < height
    if inside:
        draw = ImageDraw.Draw(image)
        r = 7
        draw.ellipse((x_img - r, y_img - r, x_img + r, y_img + r), fill=(255, 0, 0), outline=(255, 255, 255), width=2)

    return {
        "image_x": x_img,
        "image_y": y_img,
        "global_x": x_global,
        "global_y": y_global,
        "inside_image": inside,
    }


# ------------- Normalization helpers -------------
def _normalize_piece(piece: str) -> str:
    if not piece:
        return piece
    for zw in _ZW_CHARS:
        piece = piece.replace(zw, "")
    piece = piece.replace("\u00A0", " ")
    piece = re.sub(r" {2,}", " ", piece)
    return piece


# ------------- Config fetch for standalone use -------------
def _fetch_tada_config(base_url: str = "http://localhost:8000") -> dict:
    """Fetch tabracadabra config from Tada settings. Falls back to env vars on error."""
    defaults = {
        "model": os.getenv("MODEL", "gemini/gemini-3.1-flash-lite-preview"),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "tada_base_url": base_url,
    }
    try:
        req = urllib.request.Request(
            f"{base_url}/api/settings",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
        defaults["model"] = data.get("tabracadabra_model") or defaults["model"]
        defaults["api_key"] = data.get("tabracadabra_api_key") or data.get("default_llm_api_key") or defaults["api_key"]
    except Exception as e:
        print(f"[tabracadabra] Could not fetch config from Tada ({e}), using defaults.")
    return defaults


class TabracadabraService:
    """Manages the Tab-key event tap lifecycle in a dedicated thread."""

    def __init__(self, config: dict, prompt_text: str, placeholder: bool = False):
        self._model = config["model"]
        self._api_key = config.get("api_key", "")
        self._tada_base_url = config.get("tada_base_url", "http://localhost:8000")
        self._prompt_text = prompt_text
        self._placeholder = placeholder

        # Thread & lifecycle
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._run_loop_ref = None  # CFRunLoop reference for stopping

        # Event tap reference
        self._tap_ref = None

        # I/O lock
        self._io_lock = threading.RLock()

        # Session state
        self._session_active = False
        self._inserted_len = 0
        self._keep_contents = False
        self._stream_thread: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._spinner_count = 0
        self._last_char_space = False
        self._content_started = False
        self._first_piece_event: threading.Event | None = None
        self._spinner_thread: threading.Thread | None = None
        self._spinner_active = False
        self._watching = False  # True while generation is active (any key/click cancels)

    # ------------- Lifecycle -------------
    def start(self):
        """Spawn a daemon thread that creates the event tap and runs the CFRunLoop."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_event_tap, daemon=True, name="tabracadabra")
        self._thread.start()
        print(f"[tabracadabra] Service started | model={self._model} | trigger=Option+Tab")

    def stop(self, timeout: float = 2.0):
        """Stop the event tap and join the thread."""
        self._stop_event.set()
        self._clear_suppress_flag()

        # Cancel any active streaming
        if self._cancel_event:
            self._cancel_event.set()

        # Disable the tap
        if self._tap_ref is not None:
            Quartz.CGEventTapEnable(self._tap_ref, False)

        # Unblock CFRunLoopRun
        if self._run_loop_ref is not None:
            Quartz.CFRunLoopStop(self._run_loop_ref)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        print("[tabracadabra] Service stopped")

    def _run_event_tap(self):
        """Create the event tap and run the CFRunLoop (blocks until stopped)."""
        mask = (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) |
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp) |
                Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown) |
                Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown) |
                Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown))
        self._tap_ref = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._callback,
            None
        )
        if not self._tap_ref:
            print("[tabracadabra] Failed to create event tap. Check Accessibility permissions.")
            return

        src = Quartz.CFMachPortCreateRunLoopSource(None, self._tap_ref, 0)
        self._run_loop_ref = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._run_loop_ref, src, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap_ref, True)

        print("[tabracadabra] Event tap active. Press Option+Tab to generate.")
        Quartz.CFRunLoopRun()

    # ------------- Event posting helpers -------------
    def _post_event(self, ev):
        Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGEventSourceUserData, OUR_EVENT_TAG)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, ev)

    # ------------- Typing helpers -------------
    def _keyboard_text_insert(self, s: str):
        if not s:
            return
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
        with self._io_lock:
            down = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(down, len(s), s)
            self._post_event(down)
            up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
            self._post_event(up)

    def _type_text(self, s: str):
        self._keyboard_text_insert(s)

    def _press_backspace(self, times: int):
        if times <= 0:
            return
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
        with self._io_lock:
            for _ in range(times):
                down = Quartz.CGEventCreateKeyboardEvent(src, KC_BACKSPACE, True)
                self._post_event(down)
                up = Quartz.CGEventCreateKeyboardEvent(src, KC_BACKSPACE, False)
                self._post_event(up)

    def _safe_type_piece(self, piece: str):
        if not piece:
            return
        piece = _normalize_piece(piece)
        if self._last_char_space and piece.startswith(" "):
            piece = piece[1:]
        if not piece:
            return
        self._type_text(piece)
        self._inserted_len += len(piece)
        self._last_char_space = (piece[-1] == " ")

    # ------------- Tada prediction context -------------
    def _fetch_predictor_messages(self) -> list | None:
        """Fetch the predictor's full conversation to use as cached prefix."""
        try:
            req = urllib.request.Request(
                f"{self._tada_base_url}/api/user_models/latest_prediction",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
            if not data.get("available") or not data.get("messages"):
                return None
            return data["messages"]
        except Exception as e:
            print(f"[tabracadabra] Could not fetch predictor messages ({e})")
            return None

    def _build_messages(self):
        t_build = time.perf_counter()
        t_cap = time.perf_counter()
        data_url, cursor_info = capture_active_monitor_as_data_url()
        screenshot_ms = (time.perf_counter() - t_cap) * 1000

        t_fetch = time.perf_counter()
        predictor_messages = self._fetch_predictor_messages()
        predictor_fetch_ms = (time.perf_counter() - t_fetch) * 1000

        prompt_text = self._prompt_text
        if cursor_info is None:
            prompt_text += (
                "\n\nCursor metadata: cursor position was unavailable for this frame; "
                "do not assume a red dot location."
            )
        elif cursor_info["inside_image"]:
            prompt_text += (
                "\n\nCursor metadata: the red dot marks cursor location at "
                f"(x={cursor_info['image_x']}, y={cursor_info['image_y']}) in image pixels "
                "(origin: top-left)."
            )
        else:
            prompt_text += (
                "\n\nCursor metadata: the cursor was outside this frame at capture time "
                f"(mapped x={cursor_info['image_x']}, y={cursor_info['image_y']}); "
                "do not assume a red dot is visible."
            )

        tabracadabra_turn = {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": prompt_text},
        ]}

        build_total_ms = (time.perf_counter() - t_build) * 1000
        ctx = "yes" if predictor_messages else "no"
        n_msg = len(predictor_messages) if predictor_messages else 0
        print(
            f"[tabracadabra] timing build_messages screenshot_ms={screenshot_ms:.1f} "
            f"predictor_fetch_ms={predictor_fetch_ms:.1f} total_ms={build_total_ms:.1f} "
            f"predictor_ctx={ctx} n_prefix_msgs={n_msg}",
            flush=True,
        )

        if predictor_messages:
            return predictor_messages + [tabracadabra_turn]
        return [tabracadabra_turn]

    # ------------- Loading animation (spinner) -------------
    def _loading_spinner(self, first_piece_event: threading.Event, cancel_event: threading.Event):
        try:
            idx = 0
            display_text = SPINNER_FRAMES_HOLDING[idx]
            self._type_text(JOINER + display_text)
            self._inserted_len += 1 + len(display_text)
            self._spinner_count = 1 + len(display_text)
            self._last_char_space = False
            activated_t0 = time.monotonic()

            while not first_piece_event.is_set() and not cancel_event.is_set():
                # OS-level block — zero CPU while waiting
                cancel_event.wait(timeout=SPINNER_TICK_INTERVAL_S)
                if first_piece_event.is_set() or cancel_event.is_set():
                    break

                elapsed = time.monotonic() - activated_t0
                pct = min(100, int((elapsed / SPINNER_PROGRESS_DURATION_S) * 100))
                idx = (idx + 1) % len(SPINNER_FRAMES_HOLDING)
                next_display = f"{SPINNER_FRAMES_HOLDING[idx]} {pct:3d}%"

                if next_display == display_text:
                    continue

                self._press_backspace(len(display_text))
                self._inserted_len = max(0, self._inserted_len - len(display_text))
                self._spinner_count = max(0, self._spinner_count - len(display_text))

                self._type_text(next_display)
                self._inserted_len += len(next_display)
                self._spinner_count += len(next_display)
                display_text = next_display
        finally:
            self._spinner_active = False

    # ------------- Streaming worker -------------
    def _cleanup_spinner_if_present(self):
        sc = self._spinner_count
        if sc > 0:
            self._press_backspace(sc)
            self._inserted_len = max(0, self._inserted_len - sc)
            self._spinner_count = 0
            self._last_char_space = False

    @staticmethod
    def _drain_posted_key_events():
        """Wait briefly so asynchronous backspaces are applied before first content."""
        if POST_SPINNER_DRAIN_S > 0:
            time.sleep(POST_SPINNER_DRAIN_S)

    @staticmethod
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential_jitter(initial=1, max=20, jitter=2),
        retry=retry_if_exception_type((
            litellm.RateLimitError,
            litellm.APIConnectionError,
            litellm.InternalServerError,
            litellm.Timeout,
            httpx.ReadTimeout,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _completion_with_retry(**kwargs):
        return litellm_completion(**kwargs)

    @staticmethod
    def _log_usage(usage):
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", None) if details else None
        print(f"[tabracadabra] prompt={usage.prompt_tokens} cached={cached}", flush=True)

    def _stream_worker(self, cancel_event: threading.Event, first_piece_event: threading.Event):
        if self._placeholder:
            self._placeholder_worker(cancel_event, first_piece_event)
            return
        try:
            messages = self._build_messages()
        except Exception as e:
            print(f"[tabracadabra] {e}", flush=True)
            first_piece_event.set()
            t = self._spinner_thread
            if t and t.is_alive():
                # Wait until spinner thread fully exits so it cannot emit
                # late backspaces that clip the first completion characters.
                t.join()
            self._cleanup_spinner_if_present()
            self._clear_suppress_flag()
            self._finish_session()
            return
        first_piece_seen_local = False
        logger.info("[llm] tabracadabra")
        t_llm = time.perf_counter()
        try:
            stream = self._completion_with_retry(
                model=self._model,
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                api_key=self._api_key or None,
                metadata={"app": "tabracadabra"},
            )
            for chunk in stream:
                if cancel_event.is_set():
                    break
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    self._log_usage(usage)
                piece = chunk.choices[0].delta.content or "" if chunk.choices else ""
                if not piece:
                    continue
                if not first_piece_seen_local:
                    first_piece_seen_local = True
                    print(
                        f"[tabracadabra] timing llm ttft_ms={(time.perf_counter() - t_llm) * 1000:.1f}",
                        flush=True,
                    )
                    first_piece_event.set()
                    # Wait for spinner thread to fully stop before cleaning up,
                    # otherwise spinner can backspace between our count read and delete
                    t = self._spinner_thread
                    if t and t.is_alive():
                        t.join()
                    self._cleanup_spinner_if_present()
                    self._drain_posted_key_events()
                    self._content_started = True
                self._safe_type_piece(piece)
        finally:
            print(
                f"[tabracadabra] timing llm stream_total_ms={(time.perf_counter() - t_llm) * 1000:.1f}",
                flush=True,
            )
            if not first_piece_seen_local:
                first_piece_event.set()
                t = self._spinner_thread
                if t and t.is_alive():
                    t.join()
                self._cleanup_spinner_if_present()
                self._clear_suppress_flag()
            first_piece_event.set()
            self._finish_session()

    def _placeholder_worker(self, cancel_event: threading.Event, first_piece_event: threading.Event):
        """Fake LLM call: wait 2s then type placeholder text."""
        cancel_event.wait(timeout=2.0)
        if cancel_event.is_set():
            first_piece_event.set()
            return
        first_piece_event.set()
        t = self._spinner_thread
        if t and t.is_alive():
            t.join()
        self._cleanup_spinner_if_present()
        self._content_started = True
        for word in "Lorem ipsum dolor sit amet, consectetur adipiscing elit.".split(" "):
            if cancel_event.is_set():
                break
            self._safe_type_piece(word + " ")
            cancel_event.wait(timeout=0.05)
        self._finish_session()

    def _finish_session(self):
        """Auto-accept: stream finished naturally, clean up session state."""
        self._watching = False
        self._clear_suppress_flag()
        self._first_piece_event = None
        self._content_started = False
        self._inserted_len = 0
        self._last_char_space = False
        self._cancel_event = None

    # ------------- Tab-based control -------------
    def _start_spinner(self, cancel_event: threading.Event, first_piece_event: threading.Event):
        self._spinner_active = True
        t = threading.Thread(target=self._loading_spinner, args=(first_piece_event, cancel_event), daemon=True)
        t.start()
        self._spinner_thread = t

    @staticmethod
    def _set_suppress_flag():
        try:
            open(_SUPPRESS_FLAG, "x").close()
        except FileExistsError:
            pass

    @staticmethod
    def _clear_suppress_flag():
        try:
            os.remove(_SUPPRESS_FLAG)
        except FileNotFoundError:
            pass

    def _start_stream(self):
        self._session_active = True
        t = threading.Thread(target=self._stream_worker, args=(self._cancel_event, self._first_piece_event), daemon=True)
        self._stream_thread = t
        t.start()

    def _start_generation(self):
        """Option+Tab pressed — start spinner + LLM stream immediately."""
        self._session_active = True
        self._watching = True
        self._keep_contents = False
        self._set_suppress_flag()
        self._inserted_len = 0
        self._spinner_count = 0
        self._last_char_space = False
        self._content_started = False

        cancel = threading.Event()
        self._cancel_event = cancel
        first_piece_event = threading.Event()
        self._first_piece_event = first_piece_event

        self._start_spinner(cancel, first_piece_event)
        self._start_stream()
        print("[tabracadabra] Option+Tab: generation started", flush=True)

    def _stop_stream(self, join: bool = True):
        if self._cancel_event:
            self._cancel_event.set()
        if join and self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=0.5)
        self._stream_thread = None

    def _stop_spinner_and_cleanup(self):
        if self._cancel_event and not self._cancel_event.is_set():
            self._cancel_event.set()
        t = self._spinner_thread
        if t and t.is_alive():
            t.join()
        self._cleanup_spinner_if_present()
        self._spinner_thread = None

    def _handle_cancel(self):
        """Cancel an active watching session. Delete if spinner, interrupt if content."""
        if not self._watching:
            return
        print(f"[tabracadabra] Cancel: content_started={self._content_started}", flush=True)
        self._watching = False
        if not self._content_started:
            # Still in spinner phase — delete everything
            self._stop_stream(join=False)
            self._stop_spinner_and_cleanup()
        else:
            # Content already streaming — just stop, keep what's there
            self._stop_stream(join=False)
        self._clear_suppress_flag()
        self._first_piece_event = None
        self._content_started = False
        self._inserted_len = 0
        self._last_char_space = False
        self._cancel_event = None

    # ------------- Event Tap Callback -------------
    def _callback(self, proxy, event_type, event, refcon):
        if self._stop_event.is_set():
            return event

        if event_type in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            print(f"[tabracadabra] Event tap was disabled ({event_type}), re-enabling...")
            if self._tap_ref is not None:
                Quartz.CGEventTapEnable(self._tap_ref, True)
            return event

        try:
            # Mouse clicks cancel any active watching session
            if event_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown, Quartz.kCGEventOtherMouseDown):
                if self._watching:
                    self._handle_cancel()
                return event

            if event_type in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
                tag = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
                is_ours = (tag == OUR_EVENT_TAG)

                if is_ours:
                    return event

                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                flags = Quartz.CGEventGetFlags(event)
                has_option = bool(flags & Quartz.kCGEventFlagMaskAlternate)

                if keycode == KC_TAB and has_option:
                    if event_type == Quartz.kCGEventKeyDown:
                        autorepeat = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
                        if not autorepeat and not self._watching:
                            self._start_generation()
                    # Consume both down and up for Option+Tab
                    return None

                # Any keydown during active session cancels
                if event_type == Quartz.kCGEventKeyDown and self._watching:
                    print(f"[tabracadabra] Key during watching: keycode={keycode}", flush=True)
                    self._handle_cancel()

                return event

            return event
        except Exception as e:
            print(f"[tabracadabra] EXCEPTION in callback: {e}")
            import traceback
            traceback.print_exc()
            return event


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--placeholder", action="store_true", help="Use fake LLM responses instead of real calls")
    args = parser.parse_args()

    base_url = os.getenv("TADA_BASE_URL", "http://localhost:8000")
    config = _fetch_tada_config(base_url)
    prompt_text = load_prompt()
    service = TabracadabraService(config=config, prompt_text=prompt_text, placeholder=args.placeholder)
    service.start()
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        service.stop()
