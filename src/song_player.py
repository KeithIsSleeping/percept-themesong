"""Audio playback with per-person cooldown timers."""

import os
import time
import logging
import threading

logger = logging.getLogger(__name__)

# pygame.mixer is initialized lazily to avoid import-time audio device issues
_mixer_initialized = False


def _ensure_mixer():
    """Initialize pygame mixer on first use."""
    global _mixer_initialized
    if not _mixer_initialized:
        import pygame
        pygame.mixer.init()
        _mixer_initialized = True


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
        try:
            import pygame
            if _mixer_initialized:
                pygame.mixer.music.stop()
        except Exception:
            pass

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
        """Play an audio file via PulseAudio TCP (for Bluetooth) or fallback to pygame."""
        import subprocess
        import shutil
        import os

        self._last_audio = time.time()

        env = os.environ.copy()
        env["PULSE_SERVER"] = env.get("PULSE_SERVER", "tcp:127.0.0.1:4713")

        if shutil.which("ffplay"):
            cmd = ["ffplay", "-nodisp", "-autoexit", "-volume",
                   str(int(self.volume * 100))]
            if self.max_duration:
                cmd += ["-t", str(self.max_duration)]
            cmd.append(filepath)
            self._current_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
            )
            return

        # Fallback to pygame mixer
        _ensure_mixer()
        import pygame
        pygame.mixer.music.set_volume(self.volume)
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.play(maxtime=int(self.max_duration * 1000) if self.max_duration else 0)

    def _bt_keepalive_loop(self):
        """Background thread that sends silence to prevent BT speaker from sleeping."""
        import subprocess
        import shutil
        import os

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
