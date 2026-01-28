import sys


class ActionOverlay:
    """Must be created and run on the main thread (AppKit requirement)."""

    def __init__(self):
        self._text_field = None
        self._window = None
        self._app = None

        if sys.platform != "darwin":
            return

        import AppKit
        import Foundation

        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        screen = AppKit.NSScreen.mainScreen()
        screen_frame = screen.frame()
        w, h = 400, 200
        x = screen_frame.size.width - w - 20
        y = screen_frame.size.height - h - 60

        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(x, y, w, h),
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setLevel_(AppKit.NSFloatingWindowLevel)
        window.setOpaque_(False)
        window.setBackgroundColor_(AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.75))
        window.setIgnoresMouseEvents_(True)
        window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
            AppKit.NSWindowCollectionBehaviorStationary
        )

        text_field = AppKit.NSTextField.alloc().initWithFrame_(
            Foundation.NSMakeRect(10, 10, w - 20, h - 20)
        )
        text_field.setStringValue_("Waiting for predictions...")
        text_field.setTextColor_(AppKit.NSColor.whiteColor())
        text_field.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(11, AppKit.NSFontWeightRegular))
        text_field.setBackgroundColor_(AppKit.NSColor.clearColor())
        text_field.setBezeled_(False)
        text_field.setEditable_(False)
        text_field.setSelectable_(False)
        text_field.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
        text_field.cell().setWraps_(True)

        window.contentView().addSubview_(text_field)
        window.orderFrontRegardless()

        self._window = window
        self._text_field = text_field
        self._app = app

    def run(self):
        """Blocks on the AppKit run loop. Call from main thread."""
        if self._app:
            self._app.run()

    def update(self, text):
        if self._text_field is None:
            return
        self._text_field.performSelectorOnMainThread_withObject_waitUntilDone_(
            "setStringValue:", text, False
        )

    def close(self):
        if self._app:
            self._app.performSelectorOnMainThread_withObject_waitUntilDone_(
                "stop:", None, False
            )
