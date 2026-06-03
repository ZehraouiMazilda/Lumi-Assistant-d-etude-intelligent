import streamlit as st
from datetime import datetime
from database import init_db, get_all_session_stats, get_conn

init_db()


def _delete_session(session_id):
    try:
        conn = get_conn()
        for table, col in [
            ("concentration_timeline", "session_id"),
            ("session_stats", "session_id"),
            ("chat_messages", "session_id"),
            ("voice_transcripts", "session_id"),
            ("distraction_events", "session_id"),
            ("notes", "session_id"),
            ("sources", "session_id"),
            ("sessions", "id"),
        ]:
            conn.execute(f"DELETE FROM {table} WHERE {col}=?", (session_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB ERROR] {e}", flush=True)
        return False


def _fmt_duration(secs):
    if not secs:
        return "—"
    mins = int(secs // 60)
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h}h{m:02d}"


def _fmt_date(date_str):
    try:
        d = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        return d.strftime("%d %b %Y")
    except:
        return date_str[:10] if date_str else "—"


def _score_color(s):
    if not s:
        return "#4a3560"
    if s >= 70:
        return "#22c55e"
    if s >= 45:
        return "#f97316"
    return "#ef4444"


def show():

    st.markdown(
        """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Space+Mono&family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&display=swap');

    .block-container { padding: 2rem 3rem !important; max-width: 960px !important;
                       margin: 0 auto !important; }

    /* Dot animé logo */
    .lumi-dot {
        display: inline-block; width: 10px; height: 10px;
        border-radius: 50%; background: #9b6dff;
        box-shadow: 0 0 10px #9b6dff;
        animation: lumipulse 2s ease-in-out infinite;
        vertical-align: middle; margin-right: 8px;
    }
    @keyframes lumipulse {
        0%,100%{opacity:1;box-shadow:0 0 10px #9b6dff}
        50%{opacity:0.3;box-shadow:0 0 3px #9b6dff}
    }

    /* Step cards */
    .step-card {
        background: #13101e; border: 1px solid #2d2040;
        border-radius: 14px; padding: 1.4rem 1.2rem;
        height: 100%;
    }
    .step-num { font-family:'Space Mono',monospace; font-size:0.58rem;
                color:#4a3560; letter-spacing:0.15em; margin-bottom:0.8rem; }
    .step-title { font-family:'Syne',sans-serif; font-size:0.95rem;
                  font-weight:700; color:#e0d8ff; margin-bottom:0.4rem; }
    .step-desc { font-family:'Bricolage Grotesque',sans-serif; font-size:0.8rem;
                 color:#5a4a7a; line-height:1.6; }

    /* Session card */
    .sess-card {
        background: #13101e; border: 1px solid #2d2040;
        border-radius: 14px; padding: 1.1rem 1.3rem;
        position: relative; margin-bottom: 0;
    }
    .sess-title { font-family:'Syne',sans-serif; font-size:0.95rem;
                  font-weight:700; color:#e0d8ff; margin-bottom:3px;
                  padding-right:52px; }
    .sess-summary { font-family:'Bricolage Grotesque',sans-serif; font-size:0.78rem;
                    color:#4a3560; line-height:1.5; margin-bottom:8px;
                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .sess-meta { font-family:'Space Mono',monospace; font-size:0.65rem; color:#5a4a7a; }
    .sess-score { position:absolute; top:1rem; right:1.1rem;
                  font-family:'Syne',sans-serif; font-size:1.2rem; font-weight:800; }

    /* Pills */
    .pills { display:flex; flex-wrap:wrap; gap:8px; }
    .pill { background:#13101e; border:1px solid #2d2040; border-radius:99px;
            padding:5px 14px; font-family:'Bricolage Grotesque',sans-serif;
            font-size:0.78rem; color:#9b6dff; font-weight:600; }

    /* Eyebrow */
    .eyebrow { font-family:'Space Mono',monospace; font-size:0.62rem;
               color:#9b6dff; letter-spacing:0.2em; text-transform:uppercase; }
    .section-title { font-family:'Syne',sans-serif; font-size:1.8rem;
                     font-weight:800; color:#f0eaff; letter-spacing:-0.02em;
                     margin-bottom:1.2rem; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # ── HEADER ──────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        st.markdown(
            '<span class="lumi-dot"></span><span style="font-family:Syne,sans-serif;font-size:1.3rem;font-weight:800;color:#f0eaff;">Lumi</span>',
            unsafe_allow_html=True,
        )
    with c2:
        user = st.session_state.get("user")
        if user:
            st.markdown(
                f'<div style="font-family:Space Mono,monospace;font-size:0.6rem;color:#4a3560;padding-top:8px;">Connecté : {user.get("username","")}</div>',
                unsafe_allow_html=True,
            )
    with c3:
        if st.button("Déconnexion", key="logout_btn", use_container_width=True):
            st.session_state["user"] = None
            st.session_state["page"] = "auth"
            st.rerun()

    st.divider()

    # ── HERO ────────────────────────────────────────────────
    st.markdown(
        '<div style="text-align:center;padding:2.5rem 0 2rem;">', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="eyebrow" style="text-align:center;margin-bottom:1rem;">Assistant d\'étude intelligent</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
    <div style="font-family:'Syne',sans-serif;font-size:clamp(2.5rem,5vw,4rem);
                font-weight:800;line-height:1;letter-spacing:-0.03em;
                color:#f0eaff;text-align:center;margin-bottom:0.6rem;">
        Ton cerveau mérite
    </div>
    <div style="font-family:'Syne',sans-serif;font-size:clamp(2.5rem,5vw,4rem);
                font-weight:800;line-height:1;letter-spacing:-0.03em;text-align:center;
                background:linear-gradient(90deg,#9b6dff,#c084fc,#f472b6);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                background-clip:text;margin-bottom:1.5rem;">
        mieux que du café.
    </div>
    <div style="font-family:'Bricolage Grotesque',sans-serif;font-size:1rem;
                color:#5a4a7a;text-align:center;max-width:440px;
                margin:0 auto;line-height:1.7;">
        Lumi surveille ta concentration, répond à voix haute et transforme tes révisions en <strong style="color:#9b6dff;">vraie progression</strong>.
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # ── MODE D'EMPLOI ────────────────────────────────────────
    st.markdown('<div class="eyebrow">Mode d\'emploi</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title">Comment ça marche ?</div>', unsafe_allow_html=True
    )

    steps = [
        (
            "01",
            "Upload tes cours",
            "Glisse tes PDF ou fichiers texte. Lumi lit et comprend tes documents.",
        ),
        (
            "02",
            "Dis « Lumi »",
            "Active l'assistant vocal, pose ta question. Il répond à voix haute.",
        ),
        (
            "03",
            "Active la caméra",
            "Lumi surveille tes yeux, l'orientation de ta tête et les distractions.",
        ),
        (
            "04",
            "Prends des notes",
            "Écris tes notes brutes, Lumi les corrige automatiquement.",
        ),
        (
            "05",
            "Consulte tes stats",
            "Score de concentration, alertes, conversation — tout est sauvegardé.",
        ),
        (
            "06",
            "Quitte proprement",
            "Clique Quitter pour sauvegarder et voir les analytics de session.",
        ),
    ]

    r1 = st.columns(3, gap="medium")
    for i, (num, title, desc) in enumerate(steps[:3]):
        with r1[i]:
            st.markdown(
                f'<div class="step-card"><div class="step-num">ETAPE {num}</div><div class="step-title">{title}</div><div class="step-desc">{desc}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

    r2 = st.columns(3, gap="medium")
    for i, (num, title, desc) in enumerate(steps[3:]):
        with r2[i]:
            st.markdown(
                f'<div class="step-card"><div class="step-num">ETAPE {num}</div><div class="step-title">{title}</div><div class="step-desc">{desc}</div></div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── FONCTIONNALITÉS ──────────────────────────────────────
    st.markdown('<div class="eyebrow">Fonctionnalités</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title">Tout ce que Lumi fait</div>', unsafe_allow_html=True
    )

    features = [
        "Wake word vocal",
        "Détection clignements",
        "Analyse orientation tête",
        "Score concentration",
        "Chat IA contextuel",
        "Réponses vocales",
        "Lecture PDF",
        "Correction de notes",
        "Timeline concentration",
        "Alertes intelligentes",
        "Sauvegarde session",
        "Analytics détaillés",
    ]
    st.markdown(
        '<div class="pills">'
        + "".join(f'<span class="pill">{f}</span>' for f in features)
        + "</div>",
        unsafe_allow_html=True,
    )

    st.divider()

    # ── SESSIONS ─────────────────────────────────────────────
    st.markdown(
        '<div class="eyebrow" style="text-align:center;">Historique</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title" style="text-align:center;">Mes sessions</div>',
        unsafe_allow_html=True,
    )
    
    sessions = get_all_session_stats(user_id=st.session_state["user"]["id"])

    if sessions:
        for i in range(0, len(sessions), 2):
            cols = st.columns(2, gap="medium")
            for j, col in enumerate(cols):
                if i + j >= len(sessions):
                    break
                s = sessions[i + j]
                score = s.get("score_avg") or 0
                sc = _score_color(score)
                summary = (s.get("summary") or "Pas de résumé disponible.")[:80]
                with col:
                    st.markdown(
                        f"""
                    <div class="sess-card">
                        <div class="sess-score" style="color:{sc};">{int(score)}%</div>
                        <div class="sess-title">{s['title']}</div>
                        <div class="sess-summary">{summary}</div>
                        <div class="sess-meta">
                            {_fmt_date(s.get('created_at',''))}
                            &nbsp;·&nbsp; {_fmt_duration(s.get('duration_sec',0))}
                            &nbsp;·&nbsp; {s.get('sources_count',0)} source(s)
                            &nbsp;·&nbsp; {s.get('lumi_calls',0)}x Lumi
                        </div>
                    </div>""",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        "<div style='height:0.4rem'></div>", unsafe_allow_html=True
                    )
                    ba, bb = st.columns(2, gap="small")
                    with ba:
                        if st.button(
                            "Voir les stats",
                            key=f"stats_{s['id']}",
                            use_container_width=True,
                        ):
                            st.session_state["selected_session_id"] = s["id"]
                            st.session_state["page"] = "analytics"
                            st.rerun()
                    with bb:
                        if st.button(
                            "Supprimer", key=f"del_{s['id']}", use_container_width=True
                        ):
                            st.session_state[f"confirm_{s['id']}"] = True
                    if st.session_state.get(f"confirm_{s['id']}"):
                        st.warning(f"Supprimer **{s['title']}** ?")
                        ca, cb = st.columns(2, gap="small")
                        with ca:
                            if st.button(
                                "Confirmer",
                                key=f"yes_{s['id']}",
                                use_container_width=True,
                            ):
                                _delete_session(s["id"])
                                st.session_state.pop(f"confirm_{s['id']}", None)
                                st.rerun()
                        with cb:
                            if st.button(
                                "Annuler", key=f"no_{s['id']}", use_container_width=True
                            ):
                                st.session_state.pop(f"confirm_{s['id']}", None)
                                st.rerun()
            st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
    else:
        st.markdown(
            """
        <div style="text-align:center;padding:3rem;border:1px dashed #1e1530;
                    border-radius:14px;margin:1rem 0;">
            <div style="font-family:'Syne',sans-serif;font-size:1rem;
                        font-weight:700;color:#2d2040;margin-bottom:0.4rem;">
                Aucune session pour l'instant
            </div>
            <div style="font-family:'Bricolage Grotesque',sans-serif;
                        font-size:0.82rem;color:#1e1530;">
                Lance ta première session ci-dessous.
            </div>
        </div>""",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── NOUVELLE SESSION ─────────────────────────────────────
    st.markdown(
        '<div class="eyebrow" style="text-align:center;">Nouvelle session</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-title" style="text-align:center;">Prêt à étudier ?</div>',
        unsafe_allow_html=True,
    )

    _, fc, _ = st.columns([1, 2, 1])
    with fc:
        name = st.text_input(
            "",
            placeholder="Nom de la session — ex: Algo S2",
            label_visibility="collapsed",
            key="new_session_name",
        )
        can_start = bool(name.strip())
        if st.button(
            "Lancer la session" if can_start else "Entre un nom pour démarrer",
            key="start_btn",
            use_container_width=True,
            disabled=not can_start,
        ):
            st.session_state["new_session_title"] = name.strip()
            st.session_state["session_id"] = None
            st.session_state["page"] = "session"
            st.rerun()

    st.divider()

    # ── FOOTER ───────────────────────────────────────────────
    f1, f2, f3 = st.columns([2, 1, 1], gap="large")
    with f1:
        st.markdown(
            '<span class="lumi-dot"></span><span style="font-family:Syne,sans-serif;font-weight:800;color:#f0eaff;">Lumi</span>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-family:Bricolage Grotesque,sans-serif;font-size:0.82rem;color:#2d2040;line-height:1.7;margin-top:0.5rem;max-width:260px;">Assistant d\'étude conçu pour rester concentré et analyser tes sessions.</div>',
            unsafe_allow_html=True,
        )
    with f2:
        st.markdown(
            '<div style="font-family:Space Mono,monospace;font-size:0.6rem;color:#4a3560;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:0.6rem;">Stack</div>',
            unsafe_allow_html=True,
        )
        for item in ["Streamlit", "Groq / Llama 3.1", "Whisper Large v3", "MediaPipe"]:
            st.markdown(
                f'<div style="font-family:Bricolage Grotesque,sans-serif;font-size:0.8rem;color:#4a3560;margin-bottom:4px;">{item}</div>',
                unsafe_allow_html=True,
            )
    with f3:
        st.markdown(
            '<div style="font-family:Space Mono,monospace;font-size:0.6rem;color:#4a3560;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:0.6rem;">Fonctions</div>',
            unsafe_allow_html=True,
        )
        for item in [
            "Détection concentration",
            "Réponses vocales TTS",
            "Analytics session",
            "Sauvegarde DB",
        ]:
            st.markdown(
                f'<div style="font-family:Bricolage Grotesque,sans-serif;font-size:0.8rem;color:#4a3560;margin-bottom:4px;">{item}</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div style="font-family:Space Mono,monospace;font-size:0.6rem;color:#1e1530;text-align:center;padding-top:1.5rem;">2025–2026 · Master SISE · Python · SQLite · gTTS · OpenCV</div>',
        unsafe_allow_html=True,
    )
