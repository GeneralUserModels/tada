"""System audio recorder using macOS ScreenCaptureKit."""

import logging
import platform
import threading

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


def _check_macos_version() -> None:
    ver = platform.mac_ver()[0]
    if not ver:
        raise RuntimeError("System audio capture is only supported on macOS")
    major = int(ver.split(".")[0])
    if major < 13:
        raise RuntimeError(
            f"System audio capture requires macOS 13+, found {ver}"
        )


class SystemAudioRecorder:
    """Records system audio via ScreenCaptureKit into a buffer drained by the mixer."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        _check_macos_version()
        self.sample_rate = sample_rate
        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream = None
        self._delegate = None

    def start(self) -> None:
        import objc
        import ScreenCaptureKit  # noqa: F401 — registers the framework
        from Foundation import NSObject, NSRunLoop, NSDate
        import CoreMedia

        SCShareableContent = objc.lookUpClass("SCShareableContent")
        SCStreamConfiguration = objc.lookUpClass("SCStreamConfiguration")
        SCContentFilter = objc.lookUpClass("SCContentFilter")
        SCStream = objc.lookUpClass("SCStream")

        # Get shareable content synchronously via semaphore
        event = threading.Event()
        content_holder: list = []
        error_holder: list = []

        def handler(content, error):
            if error:
                error_holder.append(error)
            else:
                content_holder.append(content)
            event.set()

        SCShareableContent.getShareableContentWithCompletionHandler_(handler)
        event.wait(timeout=10)
        if error_holder:
            raise RuntimeError(f"Failed to get shareable content: {error_holder[0]}")
        if not content_holder:
            raise RuntimeError("Timed out getting shareable content")
        content = content_holder[0]

        displays = content.displays()
        if not displays:
            raise RuntimeError("No displays found for system audio capture")

        # Configure for audio-only capture
        config = SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(True)
        config.setChannelCount_(1)
        config.setSampleRate_(self.sample_rate)
        # Minimize video overhead — we only want audio
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))

        # Filter: capture entire display audio
        display = displays[0]
        content_filter = SCContentFilter.alloc().initWithDisplay_excludingWindows_(
            display, []
        )

        # Build delegate class
        recorder = self

        class AudioDelegate(NSObject):
            def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):
                # output_type 1 = audio
                if output_type != 1:
                    return
                recorder._process_sample_buffer(sample_buffer)

        self._delegate = AudioDelegate.alloc().init()
        self._stream = SCStream.alloc().initWithFilter_configuration_delegate_(
            content_filter, config, self._delegate
        )

        add_error_holder: list = []
        add_event = threading.Event()

        def add_handler(error):
            if error:
                add_error_holder.append(error)
            add_event.set()

        self._stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._delegate, 1, None, None  # type 1 = audio, use default queue
        )
        self._stream.startCaptureWithCompletionHandler_(add_handler)
        add_event.wait(timeout=10)
        if add_error_holder:
            raise RuntimeError(f"Failed to start audio capture: {add_error_holder[0]}")

        logger.info("System audio recorder started (rate=%d)", self.sample_rate)

    def stop(self) -> None:
        if self._stream is not None:
            event = threading.Event()
            self._stream.stopCaptureWithCompletionHandler_(lambda err: event.set())
            event.wait(timeout=5)
            self._stream = None
            self._delegate = None
        logger.info("System audio recorder stopped")

    def read_and_clear(self) -> np.ndarray | None:
        """Return accumulated samples and reset the buffer. Returns None if empty."""
        with self._lock:
            if not self._buffer:
                return None
            data = np.concatenate(self._buffer)
            self._buffer.clear()
        return data

    def _process_sample_buffer(self, sample_buffer) -> None:
        """Extract PCM float32 samples from a CMSampleBuffer."""
        import CoreMedia

        block_buffer = CoreMedia.CMSampleBufferGetDataBuffer(sample_buffer)
        if block_buffer is None:
            return

        length = CoreMedia.CMBlockBufferGetDataLength(block_buffer)
        if length == 0:
            return

        # CMBlockBufferCopyDataBytes returns (OSStatus, bytes)
        result = CoreMedia.CMBlockBufferCopyDataBytes(block_buffer, 0, length, None)
        if result is None:
            return
        if isinstance(result, tuple):
            status, data_bytes = result
            if status != 0 or data_bytes is None:
                return
        else:
            data_bytes = result

        # ScreenCaptureKit delivers float32 PCM
        samples = np.frombuffer(data_bytes, dtype=np.float32).copy()
        if len(samples) == 0:
            return

        with self._lock:
            self._buffer.append(samples)
