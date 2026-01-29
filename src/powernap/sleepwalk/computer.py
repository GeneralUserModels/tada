import base64
import io
import time

import mss
from PIL import Image
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyController, Key


# Map common key names to pynput Key objects
SPECIAL_KEYS = {
    "return": Key.enter,
    "enter": Key.enter,
    "tab": Key.tab,
    "escape": Key.esc,
    "esc": Key.esc,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "space": Key.space,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "home": Key.home,
    "end": Key.end,
    "page_up": Key.page_up,
    "page_down": Key.page_down,
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "cmd": Key.cmd,
    "command": Key.cmd,
    "super": Key.cmd,
    "f1": Key.f1,
    "f2": Key.f2,
    "f3": Key.f3,
    "f4": Key.f4,
    "f5": Key.f5,
    "f6": Key.f6,
    "f7": Key.f7,
    "f8": Key.f8,
    "f9": Key.f9,
    "f10": Key.f10,
    "f11": Key.f11,
    "f12": Key.f12,
}


class ComputerController:

    def __init__(self):
        self.mouse = MouseController()
        self.keyboard = KeyController()

    def screenshot(self):
        """Capture primary monitor, return base64-encoded PNG string."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            img = sct.grab(monitor)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8"), monitor["width"], monitor["height"]

    def click(self, x, y):
        self.mouse.position = (x, y)
        time.sleep(0.05)
        self.mouse.click(Button.left)

    def right_click(self, x, y):
        self.mouse.position = (x, y)
        time.sleep(0.05)
        self.mouse.click(Button.right)

    def double_click(self, x, y):
        self.mouse.position = (x, y)
        time.sleep(0.05)
        self.mouse.click(Button.left, 2)

    def triple_click(self, x, y):
        self.mouse.position = (x, y)
        time.sleep(0.05)
        self.mouse.click(Button.left, 3)

    def middle_click(self, x, y):
        self.mouse.position = (x, y)
        time.sleep(0.05)
        self.mouse.click(Button.middle)

    def mouse_move(self, x, y):
        self.mouse.position = (x, y)

    def scroll(self, x, y, dx, dy):
        self.mouse.position = (x, y)
        time.sleep(0.05)
        self.mouse.scroll(dx, dy)

    def type_text(self, text):
        self.keyboard.type(text)

    def press_key(self, key_str):
        """Press and release a key. Supports special keys and combos like 'ctrl+c'."""
        parts = key_str.lower().split("+")
        keys = []
        for part in parts:
            part = part.strip()
            if part in SPECIAL_KEYS:
                keys.append(SPECIAL_KEYS[part])
            elif len(part) == 1:
                keys.append(part)
            else:
                keys.append(part)

        # Press all modifier keys, press the last key, then release in reverse
        for k in keys:
            self.keyboard.press(k)
        time.sleep(0.05)
        for k in reversed(keys):
            self.keyboard.release(k)
