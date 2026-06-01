import io
import os
import threading
import tempfile
import subprocess


def _play_alert(message: str):
    """Délègue le TTS au module sound — bloqué si Lumi est en mode actif."""
    try:
        # On utilise play_tts importé globalement depuis services.sound
        vs = get_status()
        # Bloquer seulement si Lumi parle activement (pas pendant mode actif)
        if vs.get("is_speaking"):
            return
        play_tts(message)
    except Exception:
        def _beep():
            try:
                import winsound
                winsound.Beep(880, 300)
            except: pass
        threading.Thread(target=_beep, daemon=True).start()
