"""Browser tools: navigate, read, click, type, screenshot using Chrome cookies.

All Playwright operations run on a dedicated thread since Playwright's sync API
is greenlet-bound and cannot be used from arbitrary threads (e.g. subagent threads).
"""

import tempfile
import threading
from pathlib import Path
from queue import Queue
from urllib.parse import urlparse

from .base_tool import BaseTool


class BrowserManager:
    """Proxy that runs all Playwright calls on a single dedicated thread."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._queue = Queue()       # (callable, args, result_queue)
        self._thread = None
        self._started = False

    def _start_thread(self):
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        """Dedicated thread: process browser commands sequentially."""
        while True:
            fn, args, result_q = self._queue.get()
            if fn is None:  # shutdown sentinel
                break
            try:
                result_q.put(("ok", fn(*args)))
            except Exception as e:
                result_q.put(("error", e))

    def _call(self, fn, *args):
        """Submit work to the browser thread and block until done."""
        self._start_thread()
        result_q = Queue(maxsize=1)
        self._queue.put((fn, args, result_q))
        status, value = result_q.get()
        if status == "error":
            raise value
        return value

    def _ensure_browser(self):
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = self._context.new_page()

    def _inject_cookies(self, url: str) -> str | None:
        from pycookiecheat import chrome_cookies
        domain = urlparse(url).netloc
        try:
            cookies = chrome_cookies(url, as_cookies=True)
        except Exception as e:
            return f"Warning: cookie extraction failed for {domain}: {e}"
        if cookies:
            pw_cookies = []
            for c in cookies:
                if not c.name or not c.value:
                    continue
                pw_cookies.append({
                    "name": c.name,
                    "value": c.value,
                    "domain": c.host_key,
                    "path": c.path or "/",
                    "secure": bool(c.is_secure),
                })
            self._context.add_cookies(pw_cookies)
        return None

    def _do_navigate(self, url: str, wait_until: str) -> str:
        self._ensure_browser()
        warning = self._inject_cookies(url)
        self._page.goto(url, wait_until=wait_until, timeout=30000)
        title = self._page.title()
        result = f"Navigated to: {self._page.url}\nTitle: {title}"
        if warning:
            result += f"\n{warning}"
        return result

    def _do_read_text(self, selector: str) -> str:
        self._ensure_browser()
        if not self._page.url or self._page.url == "about:blank":
            return "Error: no page loaded. Use browser_navigate first."
        element = self._page.query_selector(selector)
        if not element:
            return f"Error: selector '{selector}' not found on page."
        text = element.inner_text()
        if not text.strip():
            return f"(no visible text in '{selector}')"
        return text[:50000]

    def _do_click(self, selector: str) -> str:
        self._ensure_browser()
        self._page.click(selector, timeout=10000)
        self._page.wait_for_load_state("domcontentloaded", timeout=10000)
        return f"Clicked '{selector}'. Current URL: {self._page.url}"

    def _do_type_text(self, selector: str, text: str, press_enter: bool) -> str:
        self._ensure_browser()
        self._page.fill(selector, text, timeout=10000)
        if press_enter:
            self._page.press(selector, "Enter")
            self._page.wait_for_load_state("domcontentloaded", timeout=10000)
        return f"Typed into '{selector}'. Current URL: {self._page.url}"

    def _do_screenshot(self) -> str:
        self._ensure_browser()
        if not self._page.url or self._page.url == "about:blank":
            return "Error: no page loaded. Use browser_navigate first."
        path = Path(tempfile.mktemp(suffix=".png", prefix="browser_"))
        self._page.screenshot(path=str(path), full_page=False)
        return f"Screenshot saved: {path}"

    # Public API — safe to call from any thread

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> str:
        return self._call(self._do_navigate, url, wait_until)

    def read_text(self, selector: str = "body") -> str:
        return self._call(self._do_read_text, selector)

    def click(self, selector: str) -> str:
        return self._call(self._do_click, selector)

    def type_text(self, selector: str, text: str, press_enter: bool = False) -> str:
        return self._call(self._do_type_text, selector, text, press_enter)

    def screenshot(self) -> str:
        return self._call(self._do_screenshot)

    def shutdown(self):
        if self._started:
            self._queue.put((None, None, None))  # sentinel
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._started = False


class BrowserNavigateTool(BaseTool):
    def __init__(self, manager: BrowserManager):
        super().__init__("browser_navigate",
            "Navigate to a URL in a headless browser with your Chrome cookies/sessions.",
            {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to"},
                    "wait_until": {
                        "type": "string",
                        "enum": ["domcontentloaded", "load", "networkidle"],
                        "description": "When to consider navigation done (default: domcontentloaded)",
                    },
                },
                "required": ["url"],
            },
        )
        self._manager = manager

    def run(self, url: str, wait_until: str = "domcontentloaded"):
        return self._manager.navigate(url, wait_until)


class BrowserReadTextTool(BaseTool):
    def __init__(self, manager: BrowserManager):
        super().__init__("browser_read_text",
            "Read visible text from the current browser page. Use selector to narrow scope.",
            {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to read from (default: 'body'). "
                                       "Examples: 'main', 'article', '#content'",
                    },
                },
            },
        )
        self._manager = manager

    def run(self, selector: str = "body"):
        return self._manager.read_text(selector)


class BrowserClickTool(BaseTool):
    def __init__(self, manager: BrowserManager):
        super().__init__("browser_click",
            "Click an element on the current browser page.",
            {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the element to click"},
                },
                "required": ["selector"],
            },
        )
        self._manager = manager

    def run(self, selector: str):
        return self._manager.click(selector)


class BrowserTypeTool(BaseTool):
    def __init__(self, manager: BrowserManager):
        super().__init__("browser_type",
            "Type text into an input field on the current browser page.",
            {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input element"},
                    "text": {"type": "string", "description": "The text to type"},
                    "press_enter": {"type": "boolean", "description": "Press Enter after typing (default: false)"},
                },
                "required": ["selector", "text"],
            },
        )
        self._manager = manager

    def run(self, selector: str, text: str, press_enter: bool = False):
        return self._manager.type_text(selector, text, press_enter)


class BrowserScreenshotTool(BaseTool):
    def __init__(self, manager: BrowserManager):
        super().__init__("browser_screenshot",
            "Take a screenshot of the current browser page. Returns file path.",
            {"type": "object", "properties": {}},
        )
        self._manager = manager

    def run(self):
        return self._manager.screenshot()
