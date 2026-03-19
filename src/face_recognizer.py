"""Face recognition using OpenVINO face re-identification model."""

import os
import json
import random
import numpy as np
import logging
from openvino.runtime import Core

logger = logging.getLogger(__name__)


class FaceRecognizer:
    """Generates face embeddings and matches them against enrolled identities.

    Uses 'face-reidentification-retail-0095' which produces a 256-dimensional
    embedding vector for each face crop.
    """

    def __init__(self, model_path: str, embeddings_dir: str,
                 device: str = "MYRIAD", threshold: float = 0.5):
        self.embeddings_dir = embeddings_dir
        self.threshold = threshold
        self.known_faces = {}  # name -> list of embedding vectors

        logger.info("Loading face re-identification model: %s on %s", model_path, device)
        core = Core()
        model = core.read_model(model=model_path)
        self.compiled = core.compile_model(model=model, device_name=device)

        self.input_layer = self.compiled.input(0)
        self.output_layer = self.compiled.output(0)

        # face-reidentification-retail-0095 expects [1, 3, 128, 128]
        self.input_shape = self.input_layer.shape
        self.input_h = self.input_shape[2]
        self.input_w = self.input_shape[3]

        logger.info("Face recognizer ready (input: %dx%d, threshold: %.2f)",
                     self.input_w, self.input_h, self.threshold)

        self._load_enrolled_faces()

    def _load_enrolled_faces(self):
        """Load all enrolled face embeddings from disk."""
        self.known_faces = {}
        if not os.path.exists(self.embeddings_dir):
            os.makedirs(self.embeddings_dir, exist_ok=True)
            return

        for filename in os.listdir(self.embeddings_dir):
            if not filename.endswith(".json"):
                continue
            name = filename[:-5]  # strip .json
            filepath = os.path.join(self.embeddings_dir, filename)
            with open(filepath, "r") as f:
                data = json.load(f)
            songs = data.get("songs", [])
            if not songs and data.get("song"):
                songs = [data["song"]]
            self.known_faces[name] = {
                "embeddings": [np.array(e) for e in data["embeddings"]],
                "songs": songs,
            }
            logger.info("Loaded %d embedding(s) for '%s'", len(data["embeddings"]), name)

        logger.info("Enrolled faces loaded: %d people", len(self.known_faces))

    def get_embedding(self, frame: np.ndarray, box: tuple) -> np.ndarray:
        """Extract a face embedding from a frame given a bounding box.

        Args:
            frame: Full BGR frame
            box: (x1, y1, x2, y2) face bounding box

        Returns:
            256-dimensional normalized embedding vector
        """
        x1, y1, x2, y2 = box
        face_crop = frame[y1:y2, x1:x2]

        if face_crop.size == 0:
            return None

        input_data = self._preprocess(face_crop)
        result = self.compiled([input_data])[self.output_layer]

        # Flatten and L2-normalize
        embedding = result.flatten()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def identify(self, embedding: np.ndarray) -> tuple:
        """Match an embedding against enrolled faces.

        Requires best match to exceed threshold AND have sufficient margin
        over the second-best person to avoid false matches.

        Returns:
            (name, song_path, similarity) if matched, or (None, None, 0.0)
        """
        # Collect best similarity per person
        person_scores = {}
        for name, data in self.known_faces.items():
            best_for_person = 0.0
            for known_emb in data["embeddings"]:
                similarity = float(np.dot(embedding, known_emb))
                if similarity > best_for_person:
                    best_for_person = similarity
            person_scores[name] = best_for_person

        if not person_scores:
            return None, None, 0.0

        # Sort by similarity descending
        ranked = sorted(person_scores.items(), key=lambda x: x[1], reverse=True)
        best_name, best_similarity = ranked[0]
        second_similarity = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = best_similarity - second_similarity

        if best_similarity >= self.threshold and margin >= 0.05:
            data = self.known_faces[best_name]
            songs = data.get("songs", [])
            best_song = random.choice(songs) if songs else None
            logger.debug("Identified: %s (similarity: %.3f, margin: %.3f)",
                         best_name, best_similarity, margin)
            return best_name, best_song, best_similarity

        logger.debug("Unknown face (best: %s=%.3f, 2nd: %.3f, margin: %.3f)",
                     best_name, best_similarity, second_similarity, margin)
        return None, None, best_similarity

    def enroll(self, name: str, embeddings: list, song_path: str = None):
        """Save face embeddings for a new person.

        Args:
            name: Person's name (used as filename and lookup key)
            embeddings: List of numpy embedding vectors
            song_path: Relative path to their theme song file
        """
        filepath = os.path.join(self.embeddings_dir, f"{name}.json")
        data = {
            "name": name,
            "song": song_path,
            "embeddings": [e.tolist() for e in embeddings],
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        self.known_faces[name] = {
            "embeddings": embeddings,
            "song": song_path,
        }
        logger.info("Enrolled '%s' with %d embedding(s), song: %s", name, len(embeddings), song_path)

    def _preprocess(self, face_crop: np.ndarray) -> np.ndarray:
        """Resize and reformat a face crop for the re-id model."""
        import cv2
        resized = cv2.resize(face_crop, (self.input_w, self.input_h))
        return resized.transpose(2, 0, 1).reshape(self.input_shape).astype(np.float32)
