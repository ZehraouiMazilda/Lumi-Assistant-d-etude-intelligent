import streamlit as st
import time, av, io, os, base64
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
from database import (
    init_db, create_session, update_session,
    add_source, get_sources, delete_source,
    add_note, get_notes, delete_note,
    add_chat_message, get_chat_messages,
    add_transcript,
    add_timeline_point, init_session_stats,
    increment_alert_stat, finalize_session_stats,
    get_conn,
)
from services.vision import process_frame, shared_state, start_calibration
from services.concentration_engine import engine
from services.cursor_tracker import inject_cursor_tracker
from services.voice_detector import (
    start_listening, stop_listening,
    set_session_theme, set_callbacks,
    get_status as vd_status, play_tts,
)

init_db()
RTC_CONFIG = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

class VisionProcessor(VideoProcessorBase):
    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        return av.VideoFrame.from_ndarray(process_frame(img), format="bgr24")

def _fmt_time(sec):
    m, s = divmod(int(sec), 60)
    h, m2 = divmod(m, 60)
    return f"{h:02d}:{m2:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def _score_color(s):
    if s >= 70: return "#22c55e"
    if s >= 45: return "#f97316"
    return "#ef4444"

def _extract_pdf(raw):
    try:
        import PyPDF2
        r = PyPDF2.PdfReader(io.BytesIO(raw))
        return "\n".join(p.extract_text() or "" for p in r.pages)
    except: return ""

def _get_groq():
    import httpx
    from groq import Groq
    from dotenv import load_dotenv
    load_dotenv()
    return Groq(api_key=os.getenv("GROQ_API_KEY"), http_client=httpx.Client(verify=True))

def _groq_clean_note(raw):
    try:
        r = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":f"Corrige l'orthographe UNIQUEMENT. Réponds avec la note corrigée seulement.\n\n{raw}"}],
            max_tokens=300, temperature=0.1)
        return r.choices[0].message.content.strip()
    except: return raw

def _groq_chat(history, src_content, title):
    try:
        has_src = bool(src_content and src_content.strip())
        system = (f'Tu es Lumi, assistant d\'étude pour "{title}".\n'
            + ("Sources:\n" + src_content[:4000] if has_src else "Aucune source.")
            + "\nRéponds en 3-5 phrases complètes. Ne coupe JAMAIS une phrase. Français.")
        msgs = [{"role":"system","content":system}] + [
            {"role":m["role"],"content":m["content"]} for m in history[-10:]]
        r = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant", messages=msgs, max_tokens=500, temperature=0.7)
        return r.choices[0].message.content.strip()
    except Exception as e: return f"Erreur: {e}"

def _groq_summary(src_content, title):
    try:
        has_src = bool(src_content and src_content.strip())
        prompt = (f"Session: '{title}'\n"
            + ("Sources: " + src_content[:2000] if has_src else "Pas de sources.")
            + "\nRésumé ultra-court en 2 phrases.")
        r = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":prompt}], max_tokens=150, temperature=0.5)
        return r.choices[0].message.content.strip()
    except: return "Bonjour ! Je suis Lumi."

def _groq_tasks(src_content, title, notes):
    """Génère des tâches à faire basées sur les sources et notes."""
    try:
        notes_str = "\n".join(f"- {n['clean_text'][:80]}" for n in notes[:5]) if notes else "Aucune note"
        prompt = (f"Sujet: '{title}'\nSources: {src_content[:2000]}\nNotes: {notes_str}\n\n"
            "Génère 5 tâches concrètes à réaliser pour maîtriser ce sujet. "
            "Format JSON strict, RIEN d'autre:\n"
            '[{"task":"...","priority":"haute/moyenne/basse"},...]')
        r = _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":prompt}], max_tokens=400, temperature=0.6)
        import json
        raw = r.choices[0].message.content.strip().replace("```json","").replace("```","")
        return json.loads(raw)
    except: return []

def _get_tasks(session_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM session_tasks WHERE session_id=? ORDER BY created_at",
            (session_id,)).fetchall()
        return [dict(r) for r in rows]
    except: return []
    finally: conn.close()

def _save_tasks(session_id, tasks):
    conn = get_conn()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS session_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            priority TEXT DEFAULT 'moyenne',
            done INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        for t in tasks:
            conn.execute(
                "INSERT INTO session_tasks (session_id, task, priority) VALUES (?,?,?)",
                (session_id, t.get("task",""), t.get("priority","moyenne")))
        conn.commit()
    except Exception as e: print(f"[TASKS ERROR] {e}")
    finally: conn.close()

def _toggle_task(task_id, done):
    conn = get_conn()
    try:
        conn.execute("UPDATE session_tasks SET done=? WHERE id=?", (int(done), task_id))
        conn.commit()
    finally: conn.close()

def _delete_task(task_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM session_tasks WHERE id=?", (task_id,))
        conn.commit()
    finally: conn.close()

def _setup_voice(sid, title, src_content):
    set_session_theme(title)
    def on_question(text):
        try:
            h = get_chat_messages(sid)
            h.append({"role":"user","content":text})
            reply = _groq_chat(h, src_content, title)
            add_chat_message(sid, "user", text)
            add_chat_message(sid, "assistant", reply)
            add_transcript(sid, text, mode="lumi")
            increment_alert_stat(sid, "lumi_call")
            play_tts(reply)
            # Forcer mise à jour compteur
            st.session_state["_last_msg_count"] = len(get_chat_messages(sid)) - 1
        except Exception as e:
            print(f"[on_question error] {e}", flush=True)
    set_callbacks(on_lumi_question=on_question, on_alert=lambda m: None)
    start_listening()

def _footer():
    st.divider()
    f1, f2, f3 = st.columns([2, 1, 1], gap="large")
    with f1:
        st.markdown('<span style="font-family:Syne,sans-serif;font-weight:800;color:#f0eaff;font-size:1.1rem;">Lumi</span>', unsafe_allow_html=True)
        st.caption("Assistant d'étude · Master SISE 2025–2026")
    with f2:
        st.caption("STACK")
        for x in ["Streamlit","Groq / Llama 3.1","Whisper v3","MediaPipe"]:
            st.markdown(f'<div style="font-size:0.78rem;color:#4a3560;font-family:Bricolage Grotesque,sans-serif;">{x}</div>', unsafe_allow_html=True)
    with f3:
        st.caption("FONCTIONS")
        for x in ["Concentration","Vocal TTS","Analytics","Sauvegarde DB"]:
            st.markdown(f'<div style="font-size:0.78rem;color:#4a3560;font-family:Bricolage Grotesque,sans-serif;">{x}</div>', unsafe_allow_html=True)
    st.caption("2025–2026 · Python · SQLite · gTTS · OpenCV")

def show():
    inject_cursor_tracker()

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Space+Mono&family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&display=swap');

    /* Reset fantômes home */
    .lumi-dot,.step-card,.step-num,.step-title,.step-desc,
    .sess-card,.sess-title,.sess-summary,.sess-meta,.sess-score,
    .pills,.pill,.eyebrow,.section-title { display:none !important; }

    .block-container { padding:1rem 2.5rem 2rem !important; max-width:100% !important; }

    /* Métriques */
    [data-testid="stMetricValue"] { font-family:'Syne',sans-serif !important; font-size:1.6rem !important; font-weight:800 !important; }
    [data-testid="stMetricLabel"] { font-family:'Space Mono',monospace !important; font-size:0.55rem !important; color:#4a3560 !important; text-transform:uppercase !important; letter-spacing:0.1em !important; }
    [data-testid="metric-container"] { background:#13101e !important; border:1px solid #2d2040 !important; border-radius:12px !important; padding:0.6rem !important; }

    /* Onglets */
    .stTabs [data-baseweb="tab-list"] { justify-content:center !important; background:#0e0b1a !important; border:1px solid #1e1530 !important; border-radius:12px !important; padding:5px !important; gap:6px !important; }
    .stTabs [data-baseweb="tab"] { font-family:'Syne',sans-serif !important; font-weight:700 !important; font-size:0.85rem !important; padding:8px 24px !important; border-radius:8px !important; color:#4a3560 !important; }
    .stTabs [aria-selected="true"] { background:linear-gradient(135deg,#9b6dff,#7c4fe0) !important; color:white !important; box-shadow:0 3px 10px rgba(155,109,255,0.35) !important; }

    /* Chat stylé */
    .chat-wrap { display:flex; flex-direction:column; gap:10px; padding:6px 0; }
    .chat-row-u { display:flex; justify-content:flex-end; }
    .chat-row-l { display:flex; justify-content:flex-start; }
    .chat-bubble-u { background:linear-gradient(135deg,#9b6dff,#7c4fe0); color:#fff;
        border-radius:18px 18px 4px 18px; padding:10px 15px; max-width:75%;
        font-family:'Bricolage Grotesque',sans-serif; font-size:0.85rem; line-height:1.6; }
    .chat-bubble-l { background:#13101e; border:1px solid #2d2040; color:#e0d8ff;
        border-radius:18px 18px 18px 4px; padding:10px 15px; max-width:75%;
        font-family:'Bricolage Grotesque',sans-serif; font-size:0.85rem; line-height:1.6; }
    .chat-meta { font-family:'Space Mono',monospace; font-size:0.5rem; color:#4a3560;
        text-transform:uppercase; letter-spacing:0.1em; margin-bottom:3px; }
    .chat-meta-r { text-align:right; }

    /* Notes */
    .note-box { background:#13101e; border:1px solid #2d2040; border-radius:10px;
        padding:8px 12px; font-family:'Bricolage Grotesque',sans-serif;
        font-size:0.82rem; color:#e0d8ff; margin-bottom:5px; }

    /* Tâches */
    .task-card { background:#13101e; border:1px solid #2d2040; border-radius:10px;
        padding:9px 12px; margin-bottom:6px; display:flex;
        align-items:center; gap:10px; }
    .task-text { font-family:'Bricolage Grotesque',sans-serif; font-size:0.83rem; color:#e0d8ff; flex:1; }
    .task-text-done { text-decoration:line-through; color:#4a3560; }
    .task-badge { font-family:'Space Mono',monospace; font-size:0.5rem;
        letter-spacing:0.1em; text-transform:uppercase; padding:2px 8px;
        border-radius:99px; }
    .badge-haute { background:#3d1515; color:#ef4444; border:1px solid #7f1d1d; }
    .badge-moyenne { background:#2d1f0a; color:#f97316; border:1px solid #7c3a0a; }
    .badge-basse { background:#0d1f0d; color:#22c55e; border:1px solid #14532d; }

    /* Src name sidebar */
    .src-name { font-family:'Bricolage Grotesque',sans-serif; font-size:0.8rem;
        color:#b89aff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:2px 0; }

    @keyframes lumipulse { 0%,100%{opacity:1;box-shadow:0 0 12px #9b6dff} 50%{opacity:0.2;box-shadow:0 0 3px #9b6dff} }
    @keyframes gateplus  { 0%,100%{opacity:1;box-shadow:0 0 16px #9b6dff;transform:scale(1)} 50%{opacity:0.2;box-shadow:0 0 4px #9b6dff;transform:scale(0.6)} }
    </style>
    """, unsafe_allow_html=True)

    # ── Init ─────────────────────────────────────────────────
    if not st.session_state.get("session_id"):
        title = st.session_state.get("new_session_title", "Nouvelle session")
        sid = create_session(title, user_id=st.session_state["user"]["id"])
        init_session_stats(sid)
        st.session_state.update({
            "session_id": sid, "session_title": title,
            "session_start": None, "session_ready": False,
            "summary_done": False, "open_source": None,
            "voice_started": False, "_last_msg_count": 0,
            "_last_snapshot": time.time(), "tasks_generated": False,
        })

    sid     = st.session_state["session_id"]
    title   = st.session_state["session_title"]
    ready   = st.session_state.get("session_ready", False)
    start_t = st.session_state.get("session_start")
    elapsed = (time.time() - start_t) if start_t else 0
    sources = get_sources(sid)
    has_src = len(sources) > 0
    src_content = "\n\n".join(s.get("content","") for s in sources if s.get("content"))

    # Voice démarre dès upload
    if has_src and not st.session_state.get("voice_started"):
        _setup_voice(sid, title, src_content)
        st.session_state["voice_started"] = True

    # ── Header ───────────────────────────────────────────────
    h1, h2, h3 = st.columns([1, 2, 1])
    with h1:
        dot_anim = "animation:lumipulse 2s ease-in-out infinite;" if has_src else "opacity:0.15;"
        dot_shadow = "box-shadow:0 0 8px #9b6dff;" if has_src else ""
        st.markdown(f'<div style="display:flex;align-items:center;gap:8px;padding-top:4px;"><div style="width:8px;height:8px;border-radius:50%;background:#9b6dff;{dot_shadow}{dot_anim}"></div><span style="font-family:Syne,sans-serif;font-size:1.3rem;font-weight:800;color:#f0eaff;">Lumi</span></div>', unsafe_allow_html=True)
    with h2:
        import streamlit.components.v1 as components
        st.markdown(f'<div style="text-align:center;"><p style="font-family:Space Mono,monospace;font-size:0.58rem;color:#4a3560;margin:0 0 2px;letter-spacing:0.12em;text-transform:uppercase;">{title}</p></div>', unsafe_allow_html=True)
        if ready and start_t:
            start_ts = int(start_t)
            components.html(f"""
            <div style="text-align:center;font-family:'Space Mono',monospace;font-size:1.7rem;font-weight:700;color:#f0eaff;line-height:1;" id="t">00:00</div>
            <script>
            var s0={start_ts};
            function tick(){{
                var d=Math.floor(Date.now()/1000)-s0;
                if(d<0)d=0;
                var h=Math.floor(d/3600),m=Math.floor((d%3600)/60),s=d%60;
                var txt=h>0?String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0"):String(m).padStart(2,"0")+":"+String(s).padStart(2,"0");
                document.getElementById("t").textContent=txt;
            }}
            tick(); setInterval(tick,1000);
            </script>
            """, height=40)
        else:
            st.markdown('<div style="text-align:center;font-family:Space Mono,monospace;font-size:1.7rem;font-weight:700;color:#2d2040;">--:--</div>', unsafe_allow_html=True)
    with h3:
        if st.button("Quitter", key="quit_btn", use_container_width=True):
            summary = _groq_summary(src_content, title) if src_content else ""
            update_session(sid, duration_sec=elapsed)
            finalize_session_stats(sid, summary=summary)
            stop_listening()
            for k in ["session_id","session_title","session_start","summary_done",
                      "open_source","voice_started","new_session_title",
                      "_last_msg_count","_last_snapshot","session_ready","tasks_generated"]:
                st.session_state.pop(k, None)
            st.session_state["page"] = "home"
            st.rerun()
    st.divider()

    # ── Gate sans sources ────────────────────────────────────
    if not has_src:
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;min-height:52vh;text-align:center;">
            <div style="display:flex;align-items:center;gap:14px;margin-bottom:1.2rem;">
                <div style="width:13px;height:13px;border-radius:50%;background:#9b6dff;
                    box-shadow:0 0 16px #9b6dff;animation:gateplus 1.5s ease-in-out infinite;"></div>
                <span style="font-family:'Syne',sans-serif;font-size:2.4rem;font-weight:800;color:#f0eaff;letter-spacing:-0.02em;">Lumi</span>
            </div>
            <p style="font-family:'Bricolage Grotesque',sans-serif;font-size:0.9rem;color:#5a4a7a;margin:0 0 2rem;">
                Upload tes cours pour commencer
            </p>
        </div>
        """, unsafe_allow_html=True)
        _, uc, _ = st.columns([1, 2, 1])
        with uc:
            up = st.file_uploader("Source", type=["pdf","txt"],
                                  key="uploader_gate", label_visibility="collapsed")
            if up:
                if up.name not in [s["filename"] for s in get_sources(sid)]:
                    raw = up.read()
                    txt = _extract_pdf(raw) if up.type=="application/pdf" \
                          else raw.decode("utf-8", errors="ignore")
                    if up.type=="application/pdf":
                        st.session_state[f"pdf_{up.name}"] = raw
                    add_source(sid, up.name, txt)
                    st.rerun()
        _footer()
        return

    # ── Layout principal ──────────────────────────────────────
    sidebar, main = st.columns([1, 3], gap="large")

    # ── Sidebar ───────────────────────────────────────────────
    with sidebar:
        st.caption("SOURCES")
        to_delete = []
        for s in sources:
            c1, c2 = st.columns([1, 5])
            with c1:
                if st.checkbox("chk", key=f"chk_{s['id']}", label_visibility="collapsed"):
                    to_delete.append(s["id"])
            with c2:
                st.markdown(f'<p class="src-name">{s["filename"]}</p>', unsafe_allow_html=True)
        st.caption("AJOUTER")
        up = st.file_uploader("Source", type=["pdf","txt"],
                              key="uploader", label_visibility="collapsed")
        if up:
            if up.name not in [s["filename"] for s in get_sources(sid)]:
                raw = up.read()
                txt = _extract_pdf(raw) if up.type=="application/pdf" \
                      else raw.decode("utf-8", errors="ignore")
                if up.type=="application/pdf":
                    st.session_state[f"pdf_{up.name}"] = raw
                add_source(sid, up.name, txt)
                st.rerun()
        if to_delete:
            if st.button("Supprimer", key="del_src", use_container_width=True):
                for did in to_delete: delete_source(did)
                st.session_state["open_source"] = None
                st.rerun()

    # ── Main ──────────────────────────────────────────────────
    with main:
        cam_col, score_col = st.columns([3, 2], gap="medium")

        with cam_col:
            webrtc_streamer(key="lumi-cam", video_processor_factory=VisionProcessor,
                rtc_configuration=RTC_CONFIG,
                media_stream_constraints={"video":{"facingMode":"user"},"audio":False},
                async_processing=True)

            # Bouton Commencer — lance chrono + ready
            if not ready:
                if st.button("▶  Commencer la session", key="start_session", use_container_width=True):
                    st.session_state["session_ready"] = True
                    st.session_state["session_start"] = time.time()
                    st.session_state["_last_snapshot"] = time.time()
                    st.rerun()
            else:
                with shared_state.lock:
                    calibrated = shared_state.calibrated
                if not calibrated:
                    if st.button("Calibrer (3s)", key="calib", use_container_width=True):
                        start_calibration(); st.rerun()

        with score_col:
            with shared_state.lock:
                cam_score = shared_state.score
                cam_alert = shared_state.alert
                ear       = shared_state.ear
            engine.update_cursor(st.session_state.get("cursor_idle", 0))
            engine.update_tab(st.session_state.get("tab_visible", True))
            final = engine.compute_final(cam_score)

            st.metric("Score Global", f"{final}%" if ready else "—")
            st.progress(final / 100 if ready else 0)
            st.metric("Caméra", f"{cam_score}%" if ready else "—")
            st.metric("EAR", f"{ear:.2f}" if ready else "—")

            vs = vd_status()
            lumi_on = vs.get("lumi_mode", False)
            if lumi_on:
                st.info("Lumi actif — dis **merci Lumi** pour arrêter")
            else:
                st.caption("Dis **Lumi** pour me parler")
            if cam_alert and ready:
                st.warning(cam_alert)

    # ── Diagnostics voix ─────────────────────────────────────
    vs = vd_status()
    lumi_on = vs.get("lumi_mode", False)
    with st.expander("Diagnostics voix", expanded=True):
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Loop",  "ON"  if vs.get("running")      else "off")
        d2.metric("Enreg", "OUI" if vs.get("is_recording") else "non")
        d3.metric("Lumi",  "OUI" if lumi_on                else "non")
        d4.metric("Parle", "OUI" if vs.get("is_speaking")  else "non")
        if vs.get("last_transcript"):
            st.caption(f'"{vs["last_transcript"]}"')

    # ── 3 Onglets ─────────────────────────────────────────────
    tab_src, tab_lumi, tab_resume = st.tabs(["  Sources  ", "  Lumi  ", "  Résumé  "])

    # ── Onglet Sources ────────────────────────────────────────
    with tab_src:
        open_src = st.session_state.get("open_source")
        if not open_src:
            if sources:
                cols = st.columns(min(len(sources), 3), gap="medium")
                for i, s in enumerate(sources):
                    with cols[i % 3]:
                        st.markdown(f'<div style="background:#13101e;border:1px solid #2d2040;border-radius:12px;padding:1rem;text-align:center;"><div style="font-family:Space Mono,monospace;font-size:0.65rem;color:#4a3560;">PDF</div><div style="font-family:Bricolage Grotesque,sans-serif;font-size:0.78rem;color:#9b6dff;font-weight:600;margin-top:5px;word-break:break-all;">{s["filename"]}</div></div>', unsafe_allow_html=True)
                        if st.button("Ouvrir", key=f"open_{s['id']}", use_container_width=True):
                            st.session_state["open_source"] = s["id"]; st.rerun()
        else:
            src = next((s for s in sources if s["id"] == open_src), None)
            if not src:
                st.session_state["open_source"] = None; st.rerun(); return
            st.markdown(f'<p style="font-family:Syne,sans-serif;font-weight:700;color:#9b6dff;font-size:0.9rem;">{src["filename"]}</p>', unsafe_allow_html=True)
            pdf_b = st.session_state.get(f"pdf_{src['filename']}")
            if pdf_b and src["filename"].lower().endswith(".pdf"):
                b64 = base64.b64encode(pdf_b).decode()
                st.markdown(f'<iframe src="data:application/pdf;base64,{b64}#toolbar=1" width="100%" height="480px" style="border:1px solid #2d2040;border-radius:12px;display:block;"></iframe>', unsafe_allow_html=True)
            else:
                st.text_area("Contenu", src.get("content","")[:5000], height=300,
                             disabled=True, label_visibility="collapsed")
            st.caption("NOTES")
            for n in get_notes(sid, src["id"]):
                nc1, nc2 = st.columns([6, 1])
                with nc1:
                    st.markdown(f'<div class="note-box"><div style="font-family:Space Mono,monospace;font-size:0.52rem;color:#4a3560;">{n["created_at"][:16]}</div>{n["clean_text"]}</div>', unsafe_allow_html=True)
                with nc2:
                    if st.button("X", key=f"dn_{n['id']}"): delete_note(n["id"]); st.rerun()
            note_txt = st.text_area("Note", placeholder="Ta note ici...",
                                    label_visibility="collapsed", key=f"ni_{src['id']}", height=70)
            if st.button("Ajouter (Lumi corrige)", key=f"an_{src['id']}", use_container_width=True):
                if note_txt.strip():
                    with st.spinner("Lumi corrige..."):
                        clean = _groq_clean_note(note_txt.strip())
                    add_note(sid, note_txt.strip(), clean, src["id"]); st.rerun()
            if st.button("Retour", key="back_src"):
                st.session_state["open_source"] = None; st.rerun()

    # ── Onglet Lumi Chat ──────────────────────────────────────
    with tab_lumi:
        if not st.session_state.get("summary_done"):
            with st.spinner("Lumi prépare un résumé..."):
                summary = _groq_summary(src_content, title)
            add_chat_message(sid, "assistant", summary)
            st.session_state["summary_done"] = True

        # Chat stylé avec bulles centrées
        messages = get_chat_messages(sid)[-30:]
        st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)
        for m in messages:
            if m["role"] == "user":
                st.markdown(f'<div class="chat-row-u"><div><div class="chat-meta chat-meta-r">Toi</div><div class="chat-bubble-u">{m["content"]}</div></div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-row-l"><div><div class="chat-meta">Lumi</div><div class="chat-bubble-l">{m["content"]}</div></div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        mc, bc = st.columns([4, 1])
        with mc:
            user_input = st.text_input("Message", placeholder="Pose une question à Lumi...",
                                       label_visibility="collapsed", key="chat_input")
        with bc:
            if st.button("Envoyer", key="send", use_container_width=True):
                if user_input.strip():
                    add_chat_message(sid, "user", user_input.strip())
                    with st.spinner("Lumi réfléchit..."):
                        reply = _groq_chat(get_chat_messages(sid), src_content, title)
                    add_chat_message(sid, "assistant", reply)
                    st.rerun()

    # ── Onglet Résumé ──────────────────────────────────────────
    with tab_resume:
        resume_key = f"full_resume_{sid}"

        st.markdown('<div style="font-family:Space Mono,monospace;font-size:0.58rem;color:#9b6dff;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:0.8rem;">Résumé de session</div>', unsafe_allow_html=True)

        if resume_key not in st.session_state:
            if st.button("Générer le résumé avec Lumi", key="gen_resume", use_container_width=True):
                # Compiler toutes les données
                all_notes = get_notes(sid)
                msgs = get_chat_messages(sid)
                notes_str = "\n".join(f"- {n['clean_text']}" for n in all_notes) if all_notes else "Aucune note."
                conv_str  = "\n".join(f"{m['role'].upper()}: {m['content'][:120]}" for m in msgs[-10:]) if msgs else "Aucune conversation."
                src_str   = src_content[:3000] if src_content else "Aucune source."

                prompt = (f"Session d'étude : '{title}'\n\n"
                    f"SOURCES :\n{src_str}\n\n"
                    f"CONVERSATION AVEC LUMI :\n{conv_str}\n\n"
                    f"NOTES PRISES :\n{notes_str}\n\n"
                    "Génère un résumé complet et structuré de cette session d'étude en français. "
                    "Inclus : les points clés appris, les questions posées, les lacunes identifiées, "
                    "et 3 points à retenir absolument. Sois précis et utile. 200-300 mots.")

                with st.spinner("Lumi rédige ton résumé..."):
                    try:
                        r = _get_groq().chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=[{"role":"user","content":prompt}],
                            max_tokens=600, temperature=0.6)
                        resume_text = r.choices[0].message.content.strip()
                    except Exception as e:
                        resume_text = f"Erreur: {e}"
                st.session_state[resume_key] = resume_text
                st.rerun()
        else:
            resume_text = st.session_state[resume_key]
            st.markdown(f'<div style="background:#13101e;border:1px solid #9b6dff33;border-left:3px solid #9b6dff;border-radius:14px;padding:1.4rem 1.6rem;font-family:Bricolage Grotesque,sans-serif;font-size:0.88rem;color:#e0d8ff;line-height:1.85;white-space:pre-wrap;">{resume_text}</div>', unsafe_allow_html=True)
            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

            # Bouton télécharger
            all_notes = get_notes(sid)
            msgs = get_chat_messages(sid)
            notes_str = "\n".join(f"- {n['clean_text']}" for n in all_notes) if all_notes else "Aucune note."
            conv_str  = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in msgs) if msgs else ""
            full_doc = (f"RÉSUMÉ DE SESSION — {title}\n"
                + "="*50 + "\n\n"
                + resume_text + "\n\n"
                + "="*50 + "\n"
                + "NOTES\n" + notes_str + "\n\n"
                + "="*50 + "\n"
                + "CONVERSATION\n" + conv_str)

            st.download_button(
                label="Télécharger le résumé (.txt)",
                data=full_doc.encode("utf-8"),
                file_name=f"lumi_{title.replace(' ','_')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
            if st.button("Régénérer", key="regen_resume"):
                del st.session_state[resume_key]; st.rerun()

    # ── Footer ────────────────────────────────────────────────
    _footer()

    # ── Snapshot 30s ─────────────────────────────────────────
    if ready:
        now = time.time()
        if now - st.session_state.get("_last_snapshot", 0) >= 30:
            st.session_state["_last_snapshot"] = now
            with shared_state.lock:
                snap_score = shared_state.score; snap_ear = shared_state.ear
                snap_yaw   = shared_state.yaw;   snap_pitch = shared_state.pitch
                snap_alert = shared_state.alert_type
            vs_snap = vd_status()
            es = engine.get_status()
            add_timeline_point(sid, elapsed,
                score_global=engine.compute_final(snap_score), score_camera=snap_score,
                score_behavior=es.get("behavior_score", 100),
                ear=snap_ear, yaw=snap_yaw, pitch=snap_pitch,
                lumi_mode=vs_snap.get("lumi_mode", False))
            if snap_alert: increment_alert_stat(sid, snap_alert)

    # ── Polling : uniquement si ready ────────────────────────
    if ready:
        current_count = len(get_chat_messages(sid))
        if current_count != st.session_state.get("_last_msg_count", 0):
            st.session_state["_last_msg_count"] = current_count
            st.rerun()
        else:
            time.sleep(5); st.rerun()
