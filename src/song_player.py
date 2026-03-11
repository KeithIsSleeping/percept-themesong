"""Audio playback with per-person cooldown timers.

Uses pre-decoded WAV cache + paplay for near-instant Bluetooth playback.
Falls back to ffplay for uncached files.
"""

import os
import time
import logging
import threading
import subprocess
import shutil
import tempfile

logger = logging.getLogger(__name__)


class SongPlayer:
    """Plays theme songs with per-person cooldown to avoid repeated triggers."""

    def __init__(self, songs_dir: str, volume: float = 0.8,
                 cooldown_seconds: int = 300, stranger_song: str = None,
                 max_duration: int = None, bt_keepalive_interval: int = 300):
        self.songs_dir = songs_dir
        self.volume = volume
        self.cooldown_seconds = cooldown_seconds
        self.stranger_song = stranger_song
        self.max_duration = max_duration
        self.bt_keepalive_interval = bt_keepalive_interval
        self._last_played = {}  # name -> timestamp
        self._last_audio = time.time()  # tracks any audio output
        self._current_proc = None  # currently playing ffplay process
        self._lock = threading.Lock()
        self._keepalive_stop = threading.Event()
        self._wav_cache = {}  # original path -> pre-decoded WAV path
        self._cache_dir = tempfile.mkdtemp(prefix="theme-wav-")

        self._precache_songs()

        if self.bt_keepalive_interval and self.bt_keepalive_interval > 0:
            self._keepalive_thread = threading.Thread(
                target=self._bt_keepalive_loop, daemon=True
            )
            self._keepalive_thread.start()
            logger.info("BT keep-alive enabled (every %ds)", self.bt_keepalive_interval)

    def is_playing(self):
        """Check if a song is currently playing."""
        if self._current_proc is not None:
            if self._current_proc.poll() is None:
                return True
            self._current_proc = None
        return False

    def play(self, name: str, song_path: str = None):
        """Play a person's theme song if cooldown has elapsed.

        Args:
            name: Person's name (for cooldown tracking)
            song_path: Path to the song file. If None, looks in songs_dir/{name}.*
        """
        with self._lock:
            if self.is_playing():
                logger.debug("Song already playing, skipping")
                return False

            if not self._cooldown_elapsed(name):
                logger.debug("Cooldown active for '%s', skipping", name)
                return False

            resolved_path = self._resolve_song(name, song_path)
            if resolved_path is None:
                logger.warning("No song found for '%s'", name)
                return False

            self._play_file(resolved_path)
            self._last_played[name] = time.time()
            logger.info("🎵 Playing theme for '%s': %s", name, resolved_path)
            return True

    def play_stranger(self):
        """Play the stranger/unknown person song if configured."""
        if self.stranger_song and os.path.exists(self.stranger_song):
            if not self.is_playing() and self._cooldown_elapsed("__stranger__"):
                self._play_file(self.stranger_song)
                self._last_played["__stranger__"] = time.time()
                logger.info("🎵 Playing stranger song")
                return True
        return False

    def stop(self):
        """Stop any currently playing song and shut down keep-alive."""
        self._keepalive_stop.set()
        if self._current_proc and self._current_proc.poll() is None:
            self._current_proc.terminate()
            self._current_proc = None

    def _precache_songs(self):
        """Pre-decode all songs to WAV at startup for instant playback."""
        if not shutil.which("ffmpeg"):
            logger.warning("ffmpeg not found, skipping WAV pre-cache")
            return

        songs = []
        if os.path.isdir(self.songs_dir):
            for f in os.listdir(self.songs_dir):
                if f.lower().endswith((".mp3", ".ogg", ".flac", ".m4a")):
                    songs.append(os.path.join(self.songs_dir, f))
        if self.stranger_song and os.path.exists(self.stranger_song):
            songs.append(self.stranger_song)

        for src in songs:
            self._cache_wav(src)

        logger.info("Pre-cached %d song(s) as WAV for instant playback", len(self._wav_cache))

    def _cache_wav(self, filepath: str) -> str:
        """Convert a single audio file to WAV. Returns cached WAV path."""
        if filepath in self._wav_cache:
            return self._wav_cache[filepath]

        basename = os.path.splitext(os.path.basename(filepath))[0]
        wav_path = os.path.join(self._cache_dir, f"{basename}.wav")

        cmd = ["ffmpeg", "-y", "-i", filepath]
        if self.max_duration:
            cmd += ["-t", str(self.max_duration)]
        cmd += ["-ar", "44100", "-ac", "2", "-f", "wav", wav_path]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30)
            if os.path.exists(wav_path):
                self._wav_cache[filepath] = wav_path
                logger.debug("Cached WAV: %s -> %s", filepath, wav_path)
                return wav_path
        except Exception as e:
            logger.warning("Failed to cache %s: %s", filepath, e)
        return None

    def _cooldown_elapsed(self, name: str) -> bool:
        """Check if enough time has passed since last play for this person."""
        last = self._last_played.get(name, 0)
        return (time.time() - last) >= self.cooldown_seconds

    def _resolve_song(self, name: str, song_path: str = None) -> str:
        """Find the song file for a person."""
        # Explicit path provided
        if song_path:
            if os.path.exists(song_path):
                return song_path
            # Try relative to songs_dir
            full = os.path.join(self.songs_dir, song_path)
            if os.path.exists(full):
                return full

        # Search songs_dir for name.{mp3,wav,ogg}
        for ext in [".mp3", ".wav", ".ogg"]:
            candidate = os.path.join(self.songs_dir, f"{name}{ext}")
            if os.path.exists(candidate):
                return candidate

        return None

    def _play_file(self, filepath: str):
        """Play audio via paplay (instant, WAV cache) or ffplay fallback."""
        self._last_audio = time.time()

        env = os.environ.copy()
        env["PULSE_SERVER"] = env.get("PULSE_SERVER", "tcp:127.0.0.1:4713")

        # Try instant playback via paplay + pre-cached WAV
        wav_path = self._wav_cache.get(filepath) or self._cache_wav(filepath)
        if wav_path and shutil.which("paplay"):
            vol_str = str(int(self.volume * 65536))  # paplay uses 0-65536
            cmd = ["paplay", "--volume", vol_str, wav_path]
            self._current_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )
            return

        # Fallback: ffplay (slower startup but handles any format)
        if shutil.which("ffplay"):
            cmd = ["ffplay", "-nodisp", "-autoexit",
                   "-fflags", "nobuffer",
                   "-analyzeduration", "0", "-probesize", "32",
                   "-volume", str(int(self.volume * 100))]
            if self.max_duration:
                cmd += ["-t", str(self.max_duration)]
            cmd.append(filepath)
            self._current_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )
            return

    def _bt_keepalive_loop(self):
        """Background thread that sends silence to prevent BT speaker from sleeping."""
        while not self._keepalive_stop.wait(30):
            elapsed = time.time() - self._last_audio
            if elapsed >= self.bt_keepalive_interval:
                if shutil.which("ffplay"):
                    env = os.environ.copy()
                    env["PULSE_SERVER"] = env.get("PULSE_SERVER", "tcp:127.0.0.1:4713")
                    subprocess.Popen(
                        ["ffplay", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                         "-t", "1", "-nodisp", "-autoexit", "-loglevel", "quiet"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                    )
                    self._last_audio = time.time()
                    logger.debug("🔇 BT keep-alive silence sent")
