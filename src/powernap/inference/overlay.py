import re
import sys


class ActionOverlay:
    """Must be created and run on the main thread (AppKit requirement)."""

    _WIDTH = 420
    _MAX_HEIGHT = 500
    _MIN_HEIGHT = 80
    _SCREEN_PADDING = 20
    _BOTTOM_PADDING = 60

    def __init__(self):
        self._text_view = None
        self._scroll_view = None
        self._window = None
        self._app = None
        self._visible = False  # Start hidden, user toggles with Ctrl+H
        self._monitor = None
        self._screen_frame = None
        self._sleepwalk_callback = None

        if sys.platform != "darwin":
            return

        import AppKit
        import Foundation

        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        screen = AppKit.NSScreen.mainScreen()
        self._screen_frame = screen.frame()
        w = self._WIDTH
        h = self._MIN_HEIGHT
        x = self._screen_frame.size.width - w - self._SCREEN_PADDING
        y = self._screen_frame.size.height - self._BOTTOM_PADDING - h

        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(x, y, w, h),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setLevel_(AppKit.NSFloatingWindowLevel)
        window.setOpaque_(False)
        window.setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.78)
        )
        window.setIgnoresMouseEvents_(True)
        window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )

        # Rounded corners
        window.contentView().setWantsLayer_(True)
        window.contentView().layer().setCornerRadius_(10)
        window.contentView().layer().setMasksToBounds_(True)

        # NSScrollView + NSTextView for rich text
        scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, w, h)
        )
        scroll_view.setHasVerticalScroller_(False)
        scroll_view.setHasHorizontalScroller_(False)
        scroll_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        scroll_view.setDrawsBackground_(False)

        text_view = AppKit.NSTextView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, w, h)
        )
        text_view.setEditable_(False)
        text_view.setSelectable_(False)
        text_view.setDrawsBackground_(False)
        text_view.setTextContainerInset_(Foundation.NSMakeSize(14, 14))
        text_view.textContainer().setLineFragmentPadding_(0)

        scroll_view.setDocumentView_(text_view)
        window.contentView().addSubview_(scroll_view)

        # Initial text
        attr_str = self._make_waiting_string()
        text_view.textStorage().setAttributedString_(attr_str)

        # Don't show window at startup - user toggles with Ctrl+H
        # window.orderFrontRegardless()

        self._window = window
        self._scroll_view = scroll_view
        self._text_view = text_view
        self._app = app

        # Register global hotkeys: Ctrl+H (toggle visibility), Ctrl+G (toggle SleepWalk)
        def _on_key_event(event):
            flags = event.modifierFlags()
            ctrl_pressed = flags & AppKit.NSEventModifierFlagControl
            if not ctrl_pressed:
                return
            char = event.charactersIgnoringModifiers()
            if char == "h":
                self._toggle_visibility()
            elif char == "g" and self._sleepwalk_callback:
                self._sleepwalk_callback()

        self._monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskKeyDown, _on_key_event
        )

    # ------------------------------------------------------------------
    # Text parsing & formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_actions(text):
        """Extract individual action strings from <action>...</action> tags."""
        actions = re.findall(r"<action>(.*?)</action>", text, re.DOTALL)
        if actions:
            return [a.strip() for a in actions if a.strip()]
        # Fallback: strip any remaining XML-ish tags and return raw text
        clean = re.sub(r"<[^>]+>", "", text).strip()
        return [clean] if clean else [text.strip()]

    @staticmethod
    def _make_waiting_string():
        """Build a styled 'not ready' message."""
        import AppKit

        result = AppKit.NSMutableAttributedString.alloc().init()

        # ── Header ──
        header_font = AppKit.NSFont.systemFontOfSize_weight_(
            13, AppKit.NSFontWeightBold
        )
        header_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.5
        )
        header_attrs = {
            AppKit.NSFontAttributeName: header_font,
            AppKit.NSForegroundColorAttributeName: header_color,
        }
        header = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Not Ready\n", header_attrs
        )
        result.appendAttributedString_(header)

        # ── Separator ──
        sep_font = AppKit.NSFont.systemFontOfSize_weight_(
            6, AppKit.NSFontWeightRegular
        )
        sep_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.25
        )
        sep_attrs = {
            AppKit.NSFontAttributeName: sep_font,
            AppKit.NSForegroundColorAttributeName: sep_color,
        }
        separator = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "\u2500" * 46 + "\n\n", sep_attrs
        )
        result.appendAttributedString_(separator)

        # ── Description ──
        body_font = AppKit.NSFont.systemFontOfSize_weight_(
            11.5, AppKit.NSFontWeightRegular
        )
        body_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.5
        )
        body_attrs = {
            AppKit.NSFontAttributeName: body_font,
            AppKit.NSForegroundColorAttributeName: body_color,
        }
        body = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Still labeling data\u2026\nTry again in a moment.", body_attrs
        )
        result.appendAttributedString_(body)

        return result

    @staticmethod
    def _build_flushing_string():
        """Build a styled string showing data flush in progress."""
        import AppKit

        result = AppKit.NSMutableAttributedString.alloc().init()

        # ── Header ──
        header_font = AppKit.NSFont.systemFontOfSize_weight_(
            13, AppKit.NSFontWeightBold
        )
        header_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.55, 0.78, 0.95, 1.0  # blue
        )
        header_attrs = {
            AppKit.NSFontAttributeName: header_font,
            AppKit.NSForegroundColorAttributeName: header_color,
        }
        header = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Syncing Data\u2026\n", header_attrs
        )
        result.appendAttributedString_(header)

        # ── Separator ──
        sep_font = AppKit.NSFont.systemFontOfSize_weight_(
            6, AppKit.NSFontWeightRegular
        )
        sep_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.25
        )
        sep_attrs = {
            AppKit.NSFontAttributeName: sep_font,
            AppKit.NSForegroundColorAttributeName: sep_color,
        }
        separator = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "\u2500" * 46 + "\n\n", sep_attrs
        )
        result.appendAttributedString_(separator)

        # ── Description ──
        body_font = AppKit.NSFont.systemFontOfSize_weight_(
            11.5, AppKit.NSFontWeightRegular
        )
        body_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.7
        )
        body_attrs = {
            AppKit.NSFontAttributeName: body_font,
            AppKit.NSForegroundColorAttributeName: body_color,
        }
        body = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Labeling recent activity for fresh predictions\u2026", body_attrs
        )
        result.appendAttributedString_(body)

        return result

    @staticmethod
    def _build_attributed_string(text):
        """Parse action tags and build a styled NSAttributedString."""
        import AppKit

        actions = ActionOverlay._parse_actions(text)
        result = AppKit.NSMutableAttributedString.alloc().init()

        # ── Header ──
        header_font = AppKit.NSFont.systemFontOfSize_weight_(
            13, AppKit.NSFontWeightBold
        )
        header_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.65, 0.85, 1.0, 1.0
        )
        header_attrs = {
            AppKit.NSFontAttributeName: header_font,
            AppKit.NSForegroundColorAttributeName: header_color,
        }
        header = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Predicted Actions\n", header_attrs
        )
        result.appendAttributedString_(header)

        # ── Separator ──
        sep_font = AppKit.NSFont.systemFontOfSize_weight_(
            6, AppKit.NSFontWeightRegular
        )
        sep_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.25
        )
        sep_attrs = {
            AppKit.NSFontAttributeName: sep_font,
            AppKit.NSForegroundColorAttributeName: sep_color,
        }
        separator = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "\u2500" * 46 + "\n\n", sep_attrs
        )
        result.appendAttributedString_(separator)

        # ── Numbered actions ──
        num_font = AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(
            11.5, AppKit.NSFontWeightSemibold
        )
        num_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.55, 0.78, 0.95, 1.0
        )
        body_font = AppKit.NSFont.systemFontOfSize_weight_(
            11.5, AppKit.NSFontWeightRegular
        )
        body_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.92
        )

        num_attrs = {
            AppKit.NSFontAttributeName: num_font,
            AppKit.NSForegroundColorAttributeName: num_color,
        }
        body_attrs = {
            AppKit.NSFontAttributeName: body_font,
            AppKit.NSForegroundColorAttributeName: body_color,
        }

        for i, action in enumerate(actions, 1):
            num_part = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                f"{i}. ", num_attrs
            )
            result.appendAttributedString_(num_part)

            tail = "\n\n" if i < len(actions) else ""
            body_part = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                f"{action}{tail}", body_attrs
            )
            result.appendAttributedString_(body_part)

        return result

    @staticmethod
    def _build_sleepwalk_string(current_action, active):
        """Build a styled string for SleepWalk mode."""
        import AppKit

        result = AppKit.NSMutableAttributedString.alloc().init()

        # ── Header ──
        header_font = AppKit.NSFont.systemFontOfSize_weight_(
            13, AppKit.NSFontWeightBold
        )
        if active:
            header_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.3, 0.95, 0.55, 1.0  # green
            )
            header_text = "SleepWalk Active\n"
        else:
            header_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                1.0, 1.0, 1.0, 0.5
            )
            header_text = "SleepWalk Stopped\n"

        header_attrs = {
            AppKit.NSFontAttributeName: header_font,
            AppKit.NSForegroundColorAttributeName: header_color,
        }
        header = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            header_text, header_attrs
        )
        result.appendAttributedString_(header)

        # ── Separator ──
        sep_font = AppKit.NSFont.systemFontOfSize_weight_(
            6, AppKit.NSFontWeightRegular
        )
        sep_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.25
        )
        sep_attrs = {
            AppKit.NSFontAttributeName: sep_font,
            AppKit.NSForegroundColorAttributeName: sep_color,
        }
        separator = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "\u2500" * 46 + "\n\n", sep_attrs
        )
        result.appendAttributedString_(separator)

        if current_action:
            # ── Label ──
            label_font = AppKit.NSFont.systemFontOfSize_weight_(
                10, AppKit.NSFontWeightMedium
            )
            label_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                1.0, 0.85, 0.35, 0.8  # amber
            )
            label_attrs = {
                AppKit.NSFontAttributeName: label_font,
                AppKit.NSForegroundColorAttributeName: label_color,
            }
            label = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                "Executing:\n", label_attrs
            )
            result.appendAttributedString_(label)

            # ── Action text ──
            body_font = AppKit.NSFont.systemFontOfSize_weight_(
                11.5, AppKit.NSFontWeightRegular
            )
            body_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                1.0, 1.0, 1.0, 0.92
            )
            body_attrs = {
                AppKit.NSFontAttributeName: body_font,
                AppKit.NSForegroundColorAttributeName: body_color,
            }
            body = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                current_action, body_attrs
            )
            result.appendAttributedString_(body)
        elif active:
            wait_font = AppKit.NSFont.systemFontOfSize_weight_(
                11.5, AppKit.NSFontWeightRegular
            )
            wait_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                1.0, 1.0, 1.0, 0.5
            )
            wait_attrs = {
                AppKit.NSFontAttributeName: wait_font,
                AppKit.NSForegroundColorAttributeName: wait_color,
            }
            wait = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                "Waiting for prediction\u2026", wait_attrs
            )
            result.appendAttributedString_(wait)

        return result

    # ------------------------------------------------------------------
    # Main-thread UI updates
    # ------------------------------------------------------------------

    def _do_update(self, attr_str):
        """Set text and auto-resize window. Must run on main thread."""
        import AppKit
        import Foundation

        if self._text_view is None or self._window is None:
            return

        self._text_view.textStorage().setAttributedString_(attr_str)

        # Ask the layout manager for the real text height
        layout = self._text_view.layoutManager()
        container = self._text_view.textContainer()
        layout.ensureLayoutForTextContainer_(container)
        used = layout.usedRectForTextContainer_(container)
        inset = self._text_view.textContainerInset()
        content_h = used.size.height + inset.height * 2 + 8

        new_h = max(self._MIN_HEIGHT, min(self._MAX_HEIGHT, content_h))
        w = self._WIDTH
        x = self._screen_frame.size.width - w - self._SCREEN_PADDING
        top_y = self._screen_frame.size.height - self._BOTTOM_PADDING
        y = top_y - new_h

        self._window.setFrame_display_(
            Foundation.NSMakeRect(x, y, w, new_h), True
        )
        self._scroll_view.setFrame_(Foundation.NSMakeRect(0, 0, w, new_h))

    def _toggle_visibility(self):
        import AppKit
        from PyObjCTools import AppHelper

        if self._window is None:
            return
        if self._visible:
            self._window.performSelectorOnMainThread_withObject_waitUntilDone_(
                "orderOut:", None, False
            )
        else:
            attr_str = self._make_waiting_string()

            def _reset_and_show():
                self._do_update(attr_str)
                self._window.orderFrontRegardless()

            AppHelper.callAfter(_reset_and_show)
        self._visible = not self._visible

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self):
        """Blocks on the AppKit run loop. Call from main thread."""
        if self._app:
            self._app.run()

    def update(self, text):
        if self._text_view is None:
            return
        attr_str = self._build_attributed_string(text)
        from PyObjCTools import AppHelper

        def _on_main():
            self._do_update(attr_str)

        AppHelper.callAfter(_on_main)

    def update_flushing(self):
        """Update overlay to show data flush in progress."""
        if self._text_view is None:
            return
        attr_str = self._build_flushing_string()
        from PyObjCTools import AppHelper

        def _on_main():
            self._do_update(attr_str)

        AppHelper.callAfter(_on_main)

    def update_sleepwalk(self, current_action, active):
        if self._text_view is None:
            return
        attr_str = self._build_sleepwalk_string(current_action, active)
        from PyObjCTools import AppHelper

        def _on_main():
            self._do_update(attr_str)

        AppHelper.callAfter(_on_main)

    def set_sleepwalk_callback(self, callback):
        self._sleepwalk_callback = callback

    def close(self):
        if self._monitor:
            import AppKit

            AppKit.NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        if self._app:
            self._app.performSelectorOnMainThread_withObject_waitUntilDone_(
                "stop:", None, False
            )
