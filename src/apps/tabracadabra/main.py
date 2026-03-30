#!/usr/bin/env python3
import os
import tempfile
import threading
import time
import base64
import io
import json
import re
import urllib.request
import urllib.error
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
from litellm import completion as litellm_completion

import mss
from PIL import Image, ImageDraw

import Quartz

load_dotenv()

# ------------- Constants -------------
JOINER = "\u2060"  # WORD JOINER (plays nice with Backspace)

# Keycodes
KC_TAB = 48       # 0x30
KC_BACKSPACE = 51 # 0x33

# Tagging for our own events
OUR_EVENT_TAG = 0xC0DEFEED

# Zero-width chars for normalization
_ZW_CHARS = ("\u200B", "\u2060")

# Flag file to suppress screen connector aggregation during active streaming
_SUPPRESS_FLAG = os.path.join(tempfile.gettempdir(), "powernap_tab_active")


def load_prompt() -> str:
    """Load the tab prompt from the file next to this module."""
    prompt_path = Path(__file__).parent / "tab_prompt.txt"
    return prompt_path.read_text()


# ------------- Screenshot helpers (mss + Quartz) -------------
def _get_cursor_point():
    ev = Quartz.CGEventCreate(None)
    loc = Quartz.CGEventGetLocation(ev)
    return int(loc.x), int(loc.y)


def _find_monitor_for_point(monitors, x, y):
    for mon in monitors[1:]:
        left, top = mon["left"], mon["top"]
        right = left + mon["width"]
        bottom = top + mon["height"]
        if left <= x < right and top <= y < bottom:
            return mon
    return monitors[1] if len(monitors) > 1 else monitors[0]


def _annotate_with_cursor(img: Image.Image, mon: dict, mx: int, my: int) -> Image.Image:
    cx = mx - mon["left"]
    cy = my - mon["top"]
    cx = max(0, min(cx, img.width - 1))
    cy = max(0, min(cy, img.height - 1))

    width_mm = mon.get("width_mm")
    height_mm = mon.get("height_mm")
    if width_mm and height_mm:
        dpi_x = mon["width"] / (width_mm / 25.4)
        dpi_y = mon["height"] / (height_mm / 25.4)
        dpi = (dpi_x + dpi_y) / 2
    else:
        dpi = 96

    base_size_at_96dpi = 12
    dot_r = int((dpi / 96) * base_size_at_96dpi)
    outline_w = max(2, dot_r // 4)

    draw = ImageDraw.Draw(img, "RGBA")
    draw.ellipse(
        (cx - dot_r - outline_w, cy - dot_r - outline_w,
         cx + dot_r + outline_w, cy + dot_r + outline_w),
        fill=(255, 255, 255, 255)
    )
    draw.ellipse(
        (cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r),
        fill=(255, 0, 0, 255)
    )
    return img


def capture_active_monitor_as_data_url(max_width=1600, jpeg_quality=85):
    with mss.mss() as sct:
        mx, my = _get_cursor_point()
        mon = _find_monitor_for_point(sct.monitors, mx, my)
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.rgb)

        img = _annotate_with_cursor(img, mon, mx, my)

        out_img = img
        if out_img.width > max_width:
            ratio = max_width / out_img.width
            out_img = out_img.resize((max_width, int(out_img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        out_img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64}"
        return data_url, None


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
def _fetch_powernap_config(base_url: str = "http://localhost:8000") -> dict:
    """Fetch tabracadabra config from PowerNap settings. Falls back to env vars on error."""
    defaults = {
        "model": os.getenv("MODEL", "gemini/gemini-3-flash-preview"),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "hold_threshold": float(os.getenv("HOLD_THRESHOLD", "1.0")),
        "powernap_base_url": base_url,
    }
    try:
        req = urllib.request.Request(
            f"{base_url}/api/settings",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
        defaults["model"] = data.get("tabracadabra_model") or defaults["model"]
        defaults["api_key"] = (
            data.get("tabracadabra_api_key")
            or data.get("default_llm_api_key")
            or defaults["api_key"]
        )
        defaults["hold_threshold"] = float(
            data.get("tabracadabra_hold_threshold") or defaults["hold_threshold"]
        )
    except Exception as e:
        print(f"[tabracadabra] Could not fetch config from PowerNap ({e}), using defaults.")
    return defaults


class TabracadabraService:
    """Manages the Tab-key event tap lifecycle in a dedicated thread."""

    def __init__(self, config: dict, prompt_text: str):
        self._model = config["model"]
        self._api_key = config.get("api_key", "")
        self._hold_threshold = float(config.get("hold_threshold", 1.0))
        self._powernap_base_url = config.get("powernap_base_url", "http://localhost:8000")
        self._prompt_text = prompt_text

        # Thread & lifecycle
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._run_loop_ref = None  # CFRunLoop reference for stopping

        # Event tap reference
        self._tap_ref = None

        # I/O lock
        self._io_lock = threading.RLock()

        # Session state (replaces module-level `state` dict)
        self._session_active = False
        self._inserted_len = 0
        self._keep_contents = False
        self._stream_thread: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._spinner_count = 0
        self._last_char_space = False
        self._content_started = False
        self._tab_down = False
        self._tab_down_t0 = 0.0
        self._activated = False
        self._activation_timer: threading.Thread | None = None
        self._first_piece_event: threading.Event | None = None
        self._spinner_thread: threading.Thread | None = None
        self._spinner_active = False
        self._last_other_key_down_t = 0.0  # timestamp of last non-tab keydown
        self._combo_window = 0.5  # 0.5s window to detect key combos

    # ------------- Lifecycle -------------
    def start(self):
        """Spawn a daemon thread that creates the event tap and runs the CFRunLoop."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_event_tap, daemon=True, name="tabracadabra")
        self._thread.start()
        print(f"[tabracadabra] Service started | model={self._model} | threshold={self._hold_threshold}s")

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
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp))
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

        print("[tabracadabra] Event tap active. Hold Tab to stream, quick tap for normal Tab.")
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

    # ------------- PowerNap prediction context -------------
    def _fetch_latest_prediction(self) -> str:
        try:
            req = urllib.request.Request(
                f"{self._powernap_base_url}/api/user_models/latest_prediction",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
            if not data.get("available"):
                return ""
            parts = []
            retrieved = (data.get("retrieved") or "").strip()
            if retrieved:
                parts.append(f"### Retrieved observations:\n{retrieved}")
            revise = (data.get("revise") or "").strip()
            think = (data.get("think") or "").strip()
            reasoning = revise or think
            if reasoning:
                parts.append(f"### Reasoning about next steps:\n{reasoning}")
            actions = (data.get("actions") or "").strip()
            if actions:
                parts.append(f"### Predicted next actions:\n{actions}")
            if not parts:
                return ""
            return "## User model context:\n" + "\n\n".join(parts)
        except Exception as e:
            print(f"[tabracadabra] Could not fetch prediction context ({e}), proceeding without.")
            return ""

    def _build_messages(self):
        data_url, _ = capture_active_monitor_as_data_url()
        powernap_context = self._fetch_latest_prediction()
        prompt = self._prompt_text.format(POWERNAP_CONTEXT=powernap_context)
        return [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": prompt},
        ]}]

    # ------------- Loading animation (spinner) -------------
    def _loading_spinner(self, first_piece_event: threading.Event, cancel_event: threading.Event):
        try:
            FRAMES = ["◐", "◓", "◑", "◒"]
            INTERVAL = 0.12

            self._type_text(JOINER + FRAMES[0])
            self._inserted_len += 2
            self._spinner_count = 2
            self._last_char_space = False

            idx = 0

            def wait_with_checks(seconds: float) -> bool:
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    if first_piece_event.is_set() or cancel_event.is_set():
                        return True
                    time.sleep(0.02)
                return False

            while not first_piece_event.is_set() and not cancel_event.is_set():
                if wait_with_checks(INTERVAL):
                    break

                self._press_backspace(1)
                self._inserted_len -= 1
                self._spinner_count = max(0, self._spinner_count - 1)

                if first_piece_event.is_set() or cancel_event.is_set():
                    break

                next_frame = FRAMES[(idx + 1) % len(FRAMES)]
                self._type_text(next_frame)
                self._inserted_len += 1
                self._spinner_count += 1

                idx = (idx + 1) % len(FRAMES)
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

    def _stream_worker(self, cancel_event: threading.Event, first_piece_event: threading.Event):
        messages = self._build_messages()
        first_piece_seen_local = False
        stream = litellm_completion(
            model=self._model,
            messages=messages,
            stream=True,
            api_key=self._api_key or None,
        )
        try:
            for chunk in stream:
                if cancel_event.is_set():
                    break
                piece = chunk.choices[0].delta.content or ""
                if not piece:
                    continue
                if not first_piece_seen_local:
                    first_piece_seen_local = True
                    first_piece_event.set()
                    self._cleanup_spinner_if_present()
                    self._content_started = True
                self._safe_type_piece(piece)
        finally:
            first_piece_event.set()

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

    def _activation_timer_body(self, start_t: float, cancel_event: threading.Event):
        while True:
            if cancel_event.is_set() or not self._tab_down:
                return
            if time.monotonic() - start_t >= self._hold_threshold:
                if not self._activated:
                    self._activated = True
                    self._start_stream()
                return
            time.sleep(0.01)

    def _handle_tab_down(self):
        if self._tab_down:
            return
        self._tab_down = True
        self._tab_down_t0 = time.monotonic()
        self._activated = False
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

        at = threading.Thread(target=self._activation_timer_body, args=(self._tab_down_t0, cancel), daemon=True)
        self._activation_timer = at
        at.start()

    def _synthesize_tab_keypress(self):
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
        down = Quartz.CGEventCreateKeyboardEvent(src, KC_TAB, True)
        self._post_event(down)
        up = Quartz.CGEventCreateKeyboardEvent(src, KC_TAB, False)
        self._post_event(up)

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
            t.join(timeout=0.5)
        self._cleanup_spinner_if_present()
        self._spinner_thread = None

    def _handle_tab_up(self):
        if not self._tab_down:
            return

        self._tab_down = False
        was_activated = self._activated

        if not was_activated:
            self._stop_spinner_and_cleanup()
            self._clear_suppress_flag()
            self._synthesize_tab_keypress()
        else:
            self._keep_contents = True
            self._stop_stream(join=False)
            self._clear_suppress_flag()
            if not self._content_started:
                self._stop_spinner_and_cleanup()

        self._activation_timer = None
        self._first_piece_event = None
        self._content_started = False
        self._inserted_len = 0
        self._last_char_space = False
        self._cancel_event = None

    # ------------- Event Tap Callback -------------
    def _callback(self, proxy, event_type, event, refcon):
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            print("[tabracadabra] Event tap was disabled by timeout, re-enabling...")
            if self._tap_ref is not None:
                Quartz.CGEventTapEnable(self._tap_ref, True)
            return event

        if event_type == Quartz.kCGEventTapDisabledByUserInput:
            print("[tabracadabra] Event tap was disabled by user input, re-enabling...")
            if self._tap_ref is not None:
                Quartz.CGEventTapEnable(self._tap_ref, True)
            return event

        try:
            if event_type in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
                tag = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
                is_ours = (tag == OUR_EVENT_TAG)

                if is_ours:
                    return event

                keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)

                if keycode == KC_TAB:
                    if event_type == Quartz.kCGEventKeyDown:
                        autorepeat = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
                        if not autorepeat and not self._tab_down:
                            # If another key was pressed very recently, this is a combo (x + tab)
                            if (time.monotonic() - self._last_other_key_down_t) < self._combo_window:
                                return event
                            self._handle_tab_down()
                        return None
                    else:
                        self._handle_tab_up()
                        return None

                # Non-tab key handling
                if event_type == Quartz.kCGEventKeyDown:
                    self._last_other_key_down_t = time.monotonic()
                    # If tab is held but not yet activated, this is a combo (tab + y)
                    if self._tab_down and not self._activated:
                        self._stop_spinner_and_cleanup()
                        self._clear_suppress_flag()
                        self._tab_down = False
                        self._activation_timer = None
                        self._first_piece_event = None
                        self._cancel_event = None
                        # Synthesize the original tab before this key
                        self._synthesize_tab_keypress()

                return event

            return event
        except Exception as e:
            print(f"[tabracadabra] EXCEPTION in callback: {e}")
            import traceback
            traceback.print_exc()
            return event


if __name__ == "__main__":
    base_url = os.getenv("POWERNAP_BASE_URL", "http://localhost:8000")
    config = _fetch_powernap_config(base_url)
    prompt_text = load_prompt()
    service = TabracadabraService(config=config, prompt_text=prompt_text)
    service.start()
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        service.stop()
