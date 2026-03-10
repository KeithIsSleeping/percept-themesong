"""Face detection using OpenVINO on the Azure Percept Vision SoM."""

import numpy as np
import logging
from openvino.runtime import Core

logger = logging.getLogger(__name__)


class FaceDetector:
    """Detects faces in a frame using an OpenVINO IR model.

    Uses 'face-detection-retail-0005' by default, which outputs bounding boxes
    with confidence scores.
    """

    def __init__(self, model_path: str, device: str = "MYRIAD", confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold

        logger.info("Loading face detection model: %s on %s", model_path, device)
        core = Core()
        model = core.read_model(model=model_path)
        self.compiled = core.compile_model(model=model, device_name=device)

        self.input_layer = self.compiled.input(0)
        self.output_layer = self.compiled.output(0)

        # face-detection-retail-0005 expects [1, 3, 300, 300]
        self.input_shape = self.input_layer.shape
        self.input_h = self.input_shape[2]
        self.input_w = self.input_shape[3]

        logger.info("Face detector ready (input: %dx%d, threshold: %.2f)",
                     self.input_w, self.input_h, self.confidence_threshold)

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """Resize and reformat frame for the model."""
        resized = _resize_image(frame, self.input_w, self.input_h)
        # HWC -> NCHW, cast to float32 for OpenVINO
        return resized.transpose(2, 0, 1).reshape(self.input_shape).astype(np.float32)

    def detect(self, frame: np.ndarray) -> list:
        """Detect faces in a BGR frame.

        Returns a list of dicts: [{"box": (x1, y1, x2, y2), "confidence": float}, ...]
        Coordinates are in original frame pixel space.
        """
        h, w = frame.shape[:2]
        input_data = self._preprocess(frame)

        results = self.compiled([input_data])[self.output_layer]
        # Output shape: [1, 1, N, 7] where each detection is:
        # [image_id, label, confidence, x_min, y_min, x_max, y_max]

        faces = []
        for i in range(results.shape[2]):
            confidence = float(results[0, 0, i, 2])
            if confidence < self.confidence_threshold:
                continue

            # Extract coordinates as plain floats to avoid numpy view issues
            cx1 = float(results[0, 0, i, 3])
            cy1 = float(results[0, 0, i, 4])
            cx2 = float(results[0, 0, i, 5])
            cy2 = float(results[0, 0, i, 6])

            if not (0 <= cx1 < cx2 <= 1 and 0 <= cy1 < cy2 <= 1):
                continue

            x1 = int(cx1 * w)
            y1 = int(cy1 * h)
            x2 = int(cx2 * w)
            y2 = int(cy2 * h)

            if x2 > x1 and y2 > y1:
                faces.append({
                    "box": (x1, y1, x2, y2),
                    "confidence": confidence,
                })

        logger.debug("Detected %d face(s)", len(faces))
        return faces


def _resize_image(image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Resize image using OpenCV."""
    import cv2
    return cv2.resize(image, (target_w, target_h))
