import io
import os
import threading
import tempfile
import subprocess

def play_tts(text: str):
    def _run():
        tmp = None
        try:
            from gtts import gTTS
            buf = io.BytesIO()
            gTTS(text=str(text)[:150], lang='fr', slow=False).write_to_fp(buf)
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                f.write(buf.getvalue())
                tmp = f.name
            ps = (
                "Add-Type -AssemblyName presentationCore; "
                "$mp = New-Object System.Windows.Media.MediaPlayer; "
                f"$mp.Open([uri]'{tmp}'); "
                "$mp.Play(); "
                "Start-Sleep 1; "
                "$dur = $mp.NaturalDuration.TimeSpan.TotalSeconds; "
                "if($dur -gt 0){ Start-Sleep ([int]$dur + 1) }else{ Start-Sleep 10 }; "
                "$mp.Stop(); $mp.Close()"
            )
            subprocess.run(['powershell', '-NoProfile', '-c', ps],
                           timeout=60, capture_output=True)
        except Exception:
            try:
                import winsound
                winsound.Beep(880, 150)
            except: pass
        finally:
            if tmp:
                try: os.unlink(tmp)
                except: pass
    threading.Thread(target=_run, daemon=True).start()
