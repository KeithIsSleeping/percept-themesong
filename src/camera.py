"""Camera capture abstraction for the Azure Percept DK.

Tries multiple sources in order:
  1. USB webcam (/dev/video0, /dev/video1, etc.)
  2. RTSP stream (from azureeyemodule, if running)
  3. Static test image (for pipeline testing without a live camera)

The Vision SoM's built-in camera requires VPU attestation which is no longer
available (Azure service retired March 2023). A USB webcam plugged into the
carrier board's USB-A port is the recommended camera source.
"""

import cv2
import os
import glob
import logging
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_RTSP_URL = "rtsp://127.0.0.1:8554/raw"


class Camera:
    """Captures frames from any available camera source."""

    def __init__(self, rtsp_url: str = None, device_index: int = 0,
                 width: int = 640, height: int = 480,
                 test_image: str = None):
        self.rtsp_url = rtsp_url or DEFAULT_RTSP_URL
        self.device_index = device_index
        self.width = width
        self.height = height
        self.test_image = test_image
        self.cap = None
        self._static_frame = None
        self.source = None

    def open(self):
        """Open the best available camera source."""
        # 1. Scan for USB webcams (/dev/video*)
        video_devices = sorted(glob.glob("/dev/video*"))
        for dev in video_devices:
            idx = int(dev.replace("/dev/video", ""))
            logger.info("Trying USB webcam: %s", dev)
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    self.cap = cap
                    self.source = dev
                    logger.info("Camera opened: %s", dev)
                    return
                cap.release()

        # 2. Try RTSP (works if azureeyemodule is running)
        logger.info("No USB webcam found, trying RTSP: %s", self.rtsp_url)
        cap = cv2.VideoCapture(self.rtsp_url)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                # Verify frames aren't all-black (Vision SoM camera issue)
                if frame.mean() > 20:
                    self.cap = cap
                    self.source = f"rtsp:{self.rtsp_url}"
                    logger.info("Camera opened via RTSP")
                    return
                else:
                    logger.warning("RTSP returns black frames (mean=%.1f) — Vision SoM camera may not be working", frame.mean())
            cap.release()

        # 3. Try specified device index directly
        logger.info("Trying device index: %d", self.device_index)
        cap = cv2.VideoCapture(self.device_index)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap = cap
                self.source = f"/dev/video{self.device_index}"
                logger.info("Camera opened: /dev/video%d", self.device_index)
                return
            cap.release()

        # 4. Static test image fallback
        if self.test_image and os.path.exists(self.test_image):
            self._static_frame = cv2.imread(self.test_image)
            if self._static_frame is not None:
                self.source = f"static:{self.test_image}"
                logger.warning("Using static test image: %s", self.test_image)
                return

        raise RuntimeError(
            "No camera source available. Tried:\n"
            f"  - USB webcams: {video_devices or '(none found)'}\n"
            f"  - RTSP: {self.rtsp_url}\n"
            f"  - Device index: /dev/video{self.device_index}\n"
            f"  - Test image: {self.test_image}\n"
            "Plug a USB webcam into the carrier board USB-A port and retry."
        )

    def read(self):
        """Capture a single frame. Returns a BGR numpy array or None."""
        if self.cap is None and self._static_frame is None:
            self.open()

        if self._static_frame is not None:
            return self._static_frame.copy()

        ret, frame = self.cap.read()
        if not ret:
            logger.warning("Failed to capture frame")
            return None
        return frame

    def close(self):
        """Release the camera."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self._static_frame = None
        if self.source:
            logger.info("Camera closed (%s)", self.source)
            self.source = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
