"""Enroll a face from photo files.

Usage:
    python src/enroll_photo.py --name alice --song songs/theme.mp3 --photos photo1.jpg photo2.jpg
    python src/enroll_photo.py --name alice --song songs/theme.mp3 --photos photos/alice/

If --photos points to a directory, all .jpg/.jpeg/.png files inside are used.
"""

import argparse
import cv2
import glob
import json
import numpy as np
import os
import sys
from openvino.runtime import Core


def find_photos(paths):
    """Expand paths to a list of image files."""
    images = []
    for p in paths:
        if os.path.isdir(p):
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
                images.extend(glob.glob(os.path.join(p, ext)))
        elif os.path.isfile(p):
            images.append(p)
    return sorted(images)


def main():
    parser = argparse.ArgumentParser(description="Enroll a face from photos")
    parser.add_argument("--name", required=True, help="Person's name")
    parser.add_argument("--song", required=True, help="Path to their theme song (e.g. songs/theme.mp3)")
    parser.add_argument("--photos", nargs="+", required=True, help="Photo files or directory")
    parser.add_argument("--det-model", default="models/face-detection-retail-0005.xml")
    parser.add_argument("--reid-model", default="models/face-reidentification-retail-0095.xml")
    parser.add_argument("--output-dir", default="data/faces")
    parser.add_argument("--confidence", type=float, default=0.5, help="Min detection confidence")
    args = parser.parse_args()

    photos = find_photos(args.photos)
    if not photos:
        print(f"ERROR: No images found in {args.photos}")
        sys.exit(1)

    print(f"Enrolling: {args.name}")
    print(f"Song:      {args.song}")
    print(f"Photos:    {len(photos)} image(s)")
    print()

    core = Core()
    det = core.compile_model(core.read_model(args.det_model), "CPU")
    det_in, det_out = det.input(0), det.output(0)
    reid = core.compile_model(core.read_model(args.reid_model), "CPU")
    reid_in, reid_out = reid.input(0), reid.output(0)

    embeddings = []
    for photo_path in photos:
        frame = cv2.imread(photo_path)
        if frame is None:
            print(f"  {os.path.basename(photo_path)}: SKIP (can't read)")
            continue

        h, w = frame.shape[:2]
        blob = cv2.resize(frame, (300, 300)).transpose(2, 0, 1).reshape(1, 3, 300, 300).astype(np.float32)
        results = det([blob])[det_out]

        # Find best face
        best_conf, best_box = 0, None
        for i in range(results.shape[2]):
            conf = float(results[0, 0, i, 2])
            if conf > args.confidence and conf > best_conf:
                coords = [float(results[0, 0, i, j]) for j in range(3, 7)]
                if 0 <= coords[0] < coords[2] <= 1 and 0 <= coords[1] < coords[3] <= 1:
                    best_conf, best_box = conf, coords

        if best_box is None:
            print(f"  {os.path.basename(photo_path)}: SKIP (no face found)")
            continue

        x1, y1 = int(best_box[0] * w), int(best_box[1] * h)
        x2, y2 = int(best_box[2] * w), int(best_box[3] * h)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            print(f"  {os.path.basename(photo_path)}: SKIP (empty crop)")
            continue

        face_blob = cv2.resize(crop, (128, 128)).transpose(2, 0, 1).reshape(1, 3, 128, 128).astype(np.float32)
        emb = reid([face_blob])[reid_out].flatten()
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        embeddings.append(emb.tolist())
        print(f"  {os.path.basename(photo_path)}: OK (conf={best_conf:.3f}, face={x2-x1}x{y2-y1})")

    print()
    if len(embeddings) == 0:
        print("ERROR: No faces extracted from any photo!")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    data = {"name": args.name, "song": args.song, "embeddings": embeddings}
    out_path = os.path.join(args.output_dir, f"{args.name}.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"SUCCESS: Enrolled '{args.name}' with {len(embeddings)} embedding(s)")
    print(f"  Song: {args.song}")
    print(f"  Saved: {out_path}")


if __name__ == "__main__":
    main()
