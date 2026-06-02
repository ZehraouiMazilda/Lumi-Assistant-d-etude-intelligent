import io
import os
import threading
import tempfile

_tts_lock = threading.Lock()
_is_speaking = False

def play_tts(message: str):
    """Génère et joue un message TTS via gTTS + sounddevice."""
    global _is_speaking
    
    def _run():
        global _is_speaking
        with _tts_lock:
            _is_speaking = True
            try:
                from gtts import gTTS
                import sounddevice as sd
                import soundfile as sf

                tts = gTTS(text=message, lang="fr", slow=False)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    tmp_path = f.name
                tts.save(tmp_path)

                # Convertir mp3 → wav en mémoire via soundfile
                import subprocess
                wav_path = tmp_path.replace(".mp3", ".wav")
                subprocess.run(
                    ["ffmpeg", "-y", "-i", tmp_path, wav_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                data, samplerate = sf.read(wav_path)
                sd.play(data, samplerate)
                sd.wait()

            except Exception as e:
                print(f"[SOUND] Erreur TTS: {e}", flush=True)
            finally:
                _is_speaking = False
                try:
                    os.unlink(tmp_path)
                    os.unlink(wav_path)
                except Exception:
                    pass

    threading.Thread(target=_run, daemon=True).start()


def get_is_speaking() -> bool:
    return _is_speaking
