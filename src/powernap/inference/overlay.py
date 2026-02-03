import re
import sys


class ActionOverlay:
    """Must be created and run on the main thread (AppKit requirement)."""

    _WIDTH = 420
    _MAX_HEIGHT = 500
    _MIN_HEIGHT = 80
    _SCREEN_PADDING = 20
    _BOTTOM_PADDING = 60
    _DRAG_HANDLE_HEIGHT = 20

    def __init__(self):
        self._text_view = None
        self._scroll_view = None
        self._window = None
        self._app = None
        self._visible = True
        self._monitor = None
        self._drag_monitor = None
        self._screen_frame = None
        self._sleepwalk_callback = None
        self._drag_start_pos = None
        self._drag_start_origin = None

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
        # Bottom-left corner
        x = self._SCREEN_PADDING
        y = self._BOTTOM_PADDING

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
        # Don't ignore mouse events globally - we'll handle the drag area
        window.setIgnoresMouseEvents_(False)
        window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )

        # Rounded corners
        window.contentView().setWantsLayer_(True)
        window.contentView().layer().setCornerRadius_(10)
        window.contentView().layer().setMasksToBounds_(True)

        # Drag handle at top
        drag_handle = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, h - self._DRAG_HANDLE_HEIGHT, w, self._DRAG_HANDLE_HEIGHT)
        )
        drag_handle.setWantsLayer_(True)
        drag_handle.layer().setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 1, 1, 0.08).CGColor()
        )
        drag_handle.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin
        )
        window.contentView().addSubview_(drag_handle)
        self._drag_handle = drag_handle

        # Drag handle indicator (three dots)
        indicator = AppKit.NSTextField.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, w, self._DRAG_HANDLE_HEIGHT)
        )
        indicator.setStringValue_("\u2022 \u2022 \u2022")
        indicator.setBezeled_(False)
        indicator.setDrawsBackground_(False)
        indicator.setEditable_(False)
        indicator.setSelectable_(False)
        indicator.setAlignment_(AppKit.NSTextAlignmentCenter)
        indicator.setTextColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 1, 1, 0.3)
        )
        indicator.setFont_(AppKit.NSFont.systemFontOfSize_(8))
        drag_handle.addSubview_(indicator)

        # NSScrollView + NSTextView for rich text (below drag handle)
        content_h = h - self._DRAG_HANDLE_HEIGHT
        scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, w, content_h)
        )
        scroll_view.setHasVerticalScroller_(False)
        scroll_view.setHasHorizontalScroller_(False)
        scroll_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        scroll_view.setDrawsBackground_(False)

        text_view = AppKit.NSTextView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, w, content_h)
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

        window.orderFrontRegardless()

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

        # Register mouse events for dragging
        def _on_mouse_down(event):
            if self._window is None or not self._visible:
                return
            # Check if click is in our window's drag handle
            mouse_loc = AppKit.NSEvent.mouseLocation()
            win_frame = self._window.frame()
            handle_y = win_frame.origin.y + win_frame.size.height - self._DRAG_HANDLE_HEIGHT
            if (win_frame.origin.x <= mouse_loc.x <= win_frame.origin.x + win_frame.size.width
                    and handle_y <= mouse_loc.y <= win_frame.origin.y + win_frame.size.height):
                self._drag_start_pos = mouse_loc
                self._drag_start_origin = win_frame.origin

        def _on_mouse_dragged(event):
            if self._drag_start_pos is None:
                return
            mouse_loc = AppKit.NSEvent.mouseLocation()
            dx = mouse_loc.x - self._drag_start_pos.x
            dy = mouse_loc.y - self._drag_start_pos.y
            new_x = self._drag_start_origin.x + dx
            new_y = self._drag_start_origin.y + dy
            self._window.setFrameOrigin_(Foundation.NSMakePoint(new_x, new_y))

        def _on_mouse_up(event):
            self._drag_start_pos = None
            self._drag_start_origin = None

        self._mouse_down_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskLeftMouseDown, _on_mouse_down
        )
        self._mouse_drag_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskLeftMouseDragged, _on_mouse_dragged
        )
        self._mouse_up_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskLeftMouseUp, _on_mouse_up
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
        """Build a styled 'waiting' message."""
        import AppKit

        font = AppKit.NSFont.systemFontOfSize_weight_(12, AppKit.NSFontWeightMedium)
        color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 1.0, 1.0, 0.5
        )
        attrs = {
            AppKit.NSFontAttributeName: font,
            AppKit.NSForegroundColorAttributeName: color,
        }
        return AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Waiting for predictions\u2026", attrs
        )

    @staticmethod
    def _build_phase_string(phase):
        """Build a styled string showing the current prediction phase."""
        import AppKit

        result = AppKit.NSMutableAttributedString.alloc().init()

        # ── Header ──
        header_font = AppKit.NSFont.systemFontOfSize_weight_(
            13, AppKit.NSFontWeightBold
        )
        header_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
            1.0, 0.85, 0.35, 1.0  # amber
        )
        header_attrs = {
            AppKit.NSFontAttributeName: header_font,
            AppKit.NSForegroundColorAttributeName: header_color,
        }
        header = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "Predicting\u2026\n", header_attrs
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

        # ── Phase steps ──
        phases = ["Think", "Retrieve", "Revise", "Actions"]
        phase_idx = phases.index(phase) if phase in phases else -1

        for i, p in enumerate(phases):
            if i < phase_idx:
                # Completed
                indicator = "\u2713"  # checkmark
                ind_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.3, 0.95, 0.55, 1.0  # green
                )
                text_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1.0, 1.0, 1.0, 0.5
                )
            elif i == phase_idx:
                # Current
                indicator = "\u25B6"  # triangle
                ind_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1.0, 0.85, 0.35, 1.0  # amber
                )
                text_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1.0, 1.0, 1.0, 0.92
                )
            else:
                # Pending
                indicator = "\u25CB"  # circle
                ind_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1.0, 1.0, 1.0, 0.3
                )
                text_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1.0, 1.0, 1.0, 0.3
                )

            ind_font = AppKit.NSFont.systemFontOfSize_weight_(11, AppKit.NSFontWeightMedium)
            ind_attrs = {
                AppKit.NSFontAttributeName: ind_font,
                AppKit.NSForegroundColorAttributeName: ind_color,
            }
            ind_part = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                f"{indicator} ", ind_attrs
            )
            result.appendAttributedString_(ind_part)

            text_font = AppKit.NSFont.systemFontOfSize_weight_(11.5, AppKit.NSFontWeightRegular)
            text_attrs = {
                AppKit.NSFontAttributeName: text_font,
                AppKit.NSForegroundColorAttributeName: text_color,
            }
            tail = "\n" if i < len(phases) - 1 else ""
            text_part = AppKit.NSAttributedString.alloc().initWithString_attributes_(
                f"{p}{tail}", text_attrs
            )
            result.appendAttributedString_(text_part)

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

    def _do_update(self, attr_str, reset_position=False):
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
        text_h = used.size.height + inset.height * 2 + 8

        # Total height includes drag handle
        new_h = max(self._MIN_HEIGHT, min(self._MAX_HEIGHT, text_h + self._DRAG_HANDLE_HEIGHT))
        w = self._WIDTH

        # Get current position or reset to bottom-left
        current_frame = self._window.frame()
        if reset_position:
            x = self._SCREEN_PADDING
            y = self._BOTTOM_PADDING
        else:
            # Keep current x, adjust y to maintain top edge position
            x = current_frame.origin.x
            old_top = current_frame.origin.y + current_frame.size.height
            y = old_top - new_h

        self._window.setFrame_display_(
            Foundation.NSMakeRect(x, y, w, new_h), True
        )

        # Update scroll view to fill below drag handle
        scroll_h = new_h - self._DRAG_HANDLE_HEIGHT
        self._scroll_view.setFrame_(Foundation.NSMakeRect(0, 0, w, scroll_h))

        # Update drag handle position
        self._drag_handle.setFrame_(
            Foundation.NSMakeRect(0, scroll_h, w, self._DRAG_HANDLE_HEIGHT)
        )

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
            # Clear to waiting state and reset to bottom-left when reopening
            attr_str = self._make_waiting_string()

            def _on_main():
                self._do_update(attr_str, reset_position=True)

            AppHelper.callAfter(_on_main)
            self._window.performSelectorOnMainThread_withObject_waitUntilDone_(
                "orderFrontRegardless", None, False
            )
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

    def update_phase(self, phase):
        """Update overlay to show current prediction phase.
        
        Args:
            phase: One of "Think", "Retrieve", "Revise", "Actions"
        """
        if self._text_view is None:
            return
        attr_str = self._build_phase_string(phase)
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
        import AppKit

        if self._monitor:
            AppKit.NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        if hasattr(self, '_mouse_down_monitor') and self._mouse_down_monitor:
            AppKit.NSEvent.removeMonitor_(self._mouse_down_monitor)
            self._mouse_down_monitor = None
        if hasattr(self, '_mouse_drag_monitor') and self._mouse_drag_monitor:
            AppKit.NSEvent.removeMonitor_(self._mouse_drag_monitor)
            self._mouse_drag_monitor = None
        if hasattr(self, '_mouse_up_monitor') and self._mouse_up_monitor:
            AppKit.NSEvent.removeMonitor_(self._mouse_up_monitor)
            self._mouse_up_monitor = None
        if self._app:
            self._app.performSelectorOnMainThread_withObject_waitUntilDone_(
                "stop:", None, False
            )
