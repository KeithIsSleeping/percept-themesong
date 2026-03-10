"""Interactive face enrollment CLI.

Usage:
    python src/enroll.py --name alice --song songs/alice.mp3
    python src/enroll.py --name bob    # song auto-resolved from songs/bob.*
"""

import argparse
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

NUM_CAPTURES = 10
CAPTURE_INTERVAL = 0.8  # seconds between captures


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Enroll a face for the Theme Song system")
    parser.add_argument("--name", required=True, help="Person's name (e.g., 'alice')")
    parser.add_argument("--song", default=None, help="Path to their theme song file")
    parser.add_argument("--captures", type=int, default=NUM_CAPTURES,
                        help=f"Number of face captures (default: {NUM_CAPTURES})")
    parser.add_argument("--device", default=None, help="OpenVINO device override (CPU, MYRIAD)")
    args = parser.parse_args()

    config = load_config()
    device = args.device or config["detection"]["device"]

    print("=" * 50)
    print(f"  Face Enrollment: {args.name}")
    print("=" * 50)
    print()
    print(f"  Will capture {args.captures} photos of your face.")
    print("  Stand in front of the camera and slowly turn")
    print("  your head left and right for best results.")
    print()
    input("  Press Enter when ready...")
    print()

    camera = Camera(
        rtsp_url=config["camera"].get("rtsp_url"),
        device_index=config["camera"]["device_index"],
        width=config["camera"]["frame_width"],
        height=config["camera"]["frame_height"],
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

    embeddings = []

    with camera:
        for i in range(args.captures):
            print(f"  Capture {i + 1}/{args.captures}...", end=" ", flush=True)

            frame = camera.read()
            if frame is None:
                print("SKIP (no frame)")
                continue

            faces = detector.detect(frame)
            if len(faces) == 0:
                print("SKIP (no face detected)")
                continue

            if len(faces) > 1:
                print("SKIP (multiple faces — only you should be visible)")
                continue

            face = faces[0]
            embedding = recognizer.get_embedding(frame, face["box"])
            if embedding is not None:
                embeddings.append(embedding)
                print(f"OK (confidence: {face['confidence']:.2f})")
            else:
                print("SKIP (embedding failed)")

            time.sleep(CAPTURE_INTERVAL)

    if len(embeddings) == 0:
        print()
        print("  ❌ No faces captured! Make sure:")
        print("     - Camera is connected and working")
        print("     - You're visible and well-lit")
        print("     - Only one person is in frame")
        sys.exit(1)

    print()
    print(f"  Captured {len(embeddings)} embedding(s)")
    print(f"  Saving to: {config['recognition']['embeddings_dir']}/{args.name}.json")

    recognizer.enroll(args.name, embeddings, song_path=args.song)

    print()
    print("  ✅ Enrollment complete!")
    if args.song:
        print(f"  🎵 Theme song: {args.song}")
    else:
        print(f"  🎵 Theme song: auto-detect from songs/{args.name}.*")
    print()


if __name__ == "__main__":
    main()
