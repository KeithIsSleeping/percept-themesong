"""Theme Song Entrance System — Main Application.

Continuously watches the camera, detects and recognizes faces,
and plays personalized theme songs for known people.

Usage:
    python src/main.py
    python src/main.py --config path/to/config.yaml
"""

import argparse
import signal
import time
import sys
import os
import yaml
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.camera import Camera
from src.face_detector import FaceDetector
from src.face_recognizer import FaceRecognizer
from src.song_player import SongPlayer

logger = logging.getLogger(__name__)

running = True


def signal_handler(sig, frame):
    global running
    logger.info("Shutdown signal received")
    running = False


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Theme Song Entrance System")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--device", default=None, help="OpenVINO device override (CPU, MYRIAD)")
    parser.add_argument("--preview", action="store_true", help="Show camera preview window")
    args = parser.parse_args()

    # Resolve config path
    config_path = args.config or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"
    )
    config = load_config(config_path)

    # Setup logging
    log_level = config.get("general", {}).get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    device = args.device or config["detection"]["device"]
    show_preview = args.preview or config.get("general", {}).get("display_preview", False)
    interval = config.get("general", {}).get("detection_interval", 0.5)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize components
    logger.info("=" * 50)
    logger.info("  🎵 Theme Song Entrance System")
    logger.info("=" * 50)

    camera = Camera(
        rtsp_url=config["camera"].get("rtsp_url"),
        device_index=config["camera"]["device_index"],
        width=config["camera"]["frame_width"],
        height=config["camera"]["frame_height"],
        test_image=config["camera"].get("test_image"),
    )

    detector = FaceDetector(
        model_path=config["detection"]["model"],
        device=device,
        confidence_threshold=config["detection"]["confidence_threshold"],
    )

    recognizer = FaceRecognizer(
        model_path=config["recognition"]["model"],
        embeddings_dir=config["recognition"]["embeddings_dir"],
        device=device,
        threshold=config["recognition"]["threshold"],
    )

    player = SongPlayer(
        songs_dir=config["playback"]["songs_dir"],
        volume=config["playback"]["volume"],
        cooldown_seconds=config["playback"]["cooldown_seconds"],
        stranger_song=config["playback"].get("stranger_song"),
        max_duration=config["playback"].get("max_duration"),
        bt_keepalive_interval=config["playback"].get("bt_keepalive_interval", 300),
    )

    enrolled_count = len(recognizer.known_faces)
    logger.info("Enrolled faces: %d", enrolled_count)
    if enrolled_count == 0:
        logger.warning("No faces enrolled! Run: python src/enroll.py --name <name>")

    logger.info("Starting detection loop (interval: %.1fs)...", interval)
    logger.info("Press Ctrl+C to stop")
    print()

    stranger_streak = 0
    STRANGER_THRESHOLD = 5  # require 5 consecutive unknown detections

    with camera:
        while running:
            frame = camera.read()
            if frame is None:
                time.sleep(0.1)
                continue

            faces = detector.detect(frame)
            song_triggered = False

            for face in faces:
                embedding = recognizer.get_embedding(frame, face["box"])
                if embedding is None:
                    continue

                name, song_path, similarity = recognizer.identify(embedding)

                if name:
                    stranger_streak = 0
                    played = player.play(name, song_path)
                    if played:
                        logger.info(
                            "👋 Welcome %s! (confidence: %.2f, similarity: %.3f)",
                            name, face["confidence"], similarity,
                        )
                        song_triggered = True
                        break  # no need to check more faces
                else:
                    stranger_streak += 1
                    if stranger_streak >= STRANGER_THRESHOLD:
                        player.play_stranger()
                        stranger_streak = 0

            if not faces:
                stranger_streak = 0

            # Optional preview window (if a monitor is connected)
            if show_preview:
                import cv2
                for face in faces:
                    x1, y1, x2, y2 = face["box"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.imshow("Theme Song Cam", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            # Adaptive sleep: skip when song just triggered, short when faces
            # visible (stay responsive), full interval when idle (save CPU)
            if song_triggered:
                pass  # no delay — song is already playing
            elif faces:
                time.sleep(0.05)  # faces visible, stay responsive
            else:
                time.sleep(interval)  # idle, save CPU

    player.stop()
    logger.info("Goodbye! 🎵")


if __name__ == "__main__":
    main()
