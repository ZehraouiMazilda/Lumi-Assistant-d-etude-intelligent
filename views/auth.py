import streamlit as st
from database import init_db, create_user, login_user
from services.vision import MP_OK

init_db()

def show():
    from services.voice_detector import get_status
    vs = get_status()
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Space+Mono&family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&display=swap');

    html, body, [data-testid="stAppViewContainer"] {
        background: #0c0917 !important;
    }
    #MainMenu, footer, header { visibility: hidden !important; }
    [data-testid="stSidebar"] { display: none !important; }
    .block-container {
        padding: 0 !important;
        max-width: 100% !important;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    

    /* Inputs */
    .stTextInput input {
        background: #0e0b1a !important;
        border: 1px solid #2d2040 !important;
        border-radius: 10px !important;
        color: #f0eaff !important;
        font-family: 'Bricolage Grotesque', sans-serif !important;
        font-size: 0.88rem !important;
    }
    .stTextInput input:focus {
        border-color: #9b6dff !important;
        box-shadow: 0 0 0 2px rgba(155,109,255,0.15) !important;
    }

    /* Boutons principaux */
    .stButton > button {
        background: linear-gradient(135deg, #9b6dff, #7c4fe0) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        font-family: 'Syne', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
    }

    /* Tab buttons neutres */
    .tab-btn > button {
        background: transparent !important;
        border: 1px solid #2d2040 !important;
        color: #4a3560 !important;
        border-radius: 8px !important;
    }

    @keyframes lumipulse {
        0%,100%{opacity:1;box-shadow:0 0 14px #9b6dff}
        50%{opacity:0.2;box-shadow:0 0 3px #9b6dff}
    }
    </style>
    """, unsafe_allow_html=True)

    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "login"
    mode = st.session_state["auth_mode"]

    # ── Centrage vertical ─────────────────────────────────────
    st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.1, 1])

    with col:
        # ── Logo ─────────────────────────────────────────────
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;margin-bottom:1.8rem;">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:0.3rem;">
                <div style="width:12px;height:12px;border-radius:50%;background:#9b6dff;
                    box-shadow:0 0 14px #9b6dff;
                    animation:lumipulse 2s ease-in-out infinite;"></div>
                <span style="font-family:'Syne',sans-serif;font-size:2.2rem;font-weight:800;
                    color:#f0eaff;letter-spacing:-0.03em;">Lumi</span>
            </div>
            <span style="font-family:'Bricolage Grotesque',sans-serif;font-size:0.8rem;color:#4a3560;">
                Ton assistant d'étude intelligent
            </span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="
            background: #1a0f0f;
            border: 1px solid #7f1d1d;
            border-left: 3px solid #ef4444;
            border-radius: 10px;
            padding: 10px 16px;
            margin-bottom: 1.2rem;
            font-family: 'Bricolage Grotesque', sans-serif;
            font-size: 0.78rem;
            color: #fca5a5;
            line-height: 1.6;
        ">
            ⚠️ <strong style="color:#ef4444;">Application de démonstration</strong> — 
            Ne renseignez pas de données personnelles sensibles. 
            Cette version est à usage académique uniquement.
        </div>
        """, unsafe_allow_html=True)

        # ── Tabs ─────────────────────────────────────────────
        st.markdown("""
        <div style="background:#0e0b1a;border:1px solid #1e1530;border-radius:12px;
                    padding:5px;display:flex;gap:5px;margin-bottom:1.4rem;">
        """, unsafe_allow_html=True)

        tc1, tc2 = st.columns(2)
        with tc1:
            login_style = "background:linear-gradient(135deg,#9b6dff,#7c4fe0);color:white;box-shadow:0 3px 10px rgba(155,109,255,0.3);" if mode=="login" else "background:transparent;color:#4a3560;"
            if st.button("Connexion", key="tab_login", use_container_width=True):
                st.session_state["auth_mode"] = "login"
                st.session_state.pop("auth_error", None)
                st.rerun()
        with tc2:
            if st.button("Inscription", key="tab_register", use_container_width=True):
                st.session_state["auth_mode"] = "register"
                st.session_state.pop("auth_error", None)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Erreur ───────────────────────────────────────────
        if st.session_state.get("auth_error"):
            st.error(st.session_state["auth_error"])
        if st.session_state.get("auth_success"):
            st.success(st.session_state["auth_success"])
            st.session_state.pop("auth_success", None)

        # ── Formulaire ───────────────────────────────────────
        if mode == "login":
            st.markdown('<span style="font-family:Space Mono,monospace;font-size:0.52rem;color:#9b6dff;letter-spacing:0.18em;text-transform:uppercase;">Nom d\'utilisateur</span>', unsafe_allow_html=True)
            username = st.text_input("u", placeholder="ex: jean_dupont",
                                     label_visibility="collapsed", key="login_u")
            st.markdown('<span style="font-family:Space Mono,monospace;font-size:0.52rem;color:#9b6dff;letter-spacing:0.18em;text-transform:uppercase;">Mot de passe</span>', unsafe_allow_html=True)
            password = st.text_input("p", placeholder="••••••••", type="password",
                                     label_visibility="collapsed", key="login_p")
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

            if st.button("Se connecter →", key="do_login", use_container_width=True):
                if not username.strip() or not password.strip():
                    st.session_state["auth_error"] = "Remplis tous les champs."
                    st.rerun()
                else:
                    ok, user = login_user(username.strip(), password.strip())
                    if ok:
                        st.session_state.pop("auth_error", None)
                        st.session_state["user"] = user
                        st.session_state["page"] = "home"
                        st.rerun()
                    else:
                        st.session_state["auth_error"] = "Identifiants incorrects."
                        st.rerun()

            # Lien vers inscription — centré et stylé
            st.markdown("""
            <div style="text-align:center;margin-top:1.2rem;padding:0.8rem;
                        background:#0e0b1a;border:1px solid #1e1530;border-radius:10px;">
                <span style="font-family:'Bricolage Grotesque',sans-serif;font-size:0.78rem;color:#4a3560;">
                    Pas encore de compte ?
                </span>
                <span style="font-family:'Syne',sans-serif;font-size:0.78rem;
                             color:#9b6dff;font-weight:700;margin-left:6px;">
                    Clique sur Inscription ↑
                </span>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.markdown('<span style="font-family:Space Mono,monospace;font-size:0.52rem;color:#9b6dff;letter-spacing:0.18em;text-transform:uppercase;">Nom d\'utilisateur</span>', unsafe_allow_html=True)
            username = st.text_input("u", placeholder="ex: jean_dupont",
                                     label_visibility="collapsed", key="reg_u")
            st.markdown('<span style="font-family:Space Mono,monospace;font-size:0.52rem;color:#9b6dff;letter-spacing:0.18em;text-transform:uppercase;">Mot de passe</span>', unsafe_allow_html=True)
            password = st.text_input("p", placeholder="••••••••", type="password",
                                     label_visibility="collapsed", key="reg_p")
            st.markdown('<span style="font-family:Space Mono,monospace;font-size:0.52rem;color:#9b6dff;letter-spacing:0.18em;text-transform:uppercase;">Confirmer</span>', unsafe_allow_html=True)
            password2 = st.text_input("p2", placeholder="••••••••", type="password",
                                      label_visibility="collapsed", key="reg_p2")
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

            if st.button("Créer mon compte →", key="do_register", use_container_width=True):
                if not username.strip() or not password.strip() or not password2.strip():
                    st.session_state["auth_error"] = "Remplis tous les champs."
                    st.rerun()
                elif password != password2:
                    st.session_state["auth_error"] = "Les mots de passe ne correspondent pas."
                    st.rerun()
                elif len(password) < 6:
                    st.session_state["auth_error"] = "6 caractères minimum."
                    st.rerun()
                else:
                    ok, msg = create_user(username.strip(), password.strip())
                    if ok:
                        st.session_state["auth_success"] = "Compte créé ! Connecte-toi."
                        st.session_state["auth_mode"] = "login"
                        st.session_state.pop("auth_error", None)
                        st.rerun()
                    else:
                        st.session_state["auth_error"] = msg
                        st.rerun()

            st.markdown("""
            <div style="text-align:center;margin-top:1.2rem;padding:0.8rem;
                        background:#0e0b1a;border:1px solid #1e1530;border-radius:10px;">
                <span style="font-family:'Bricolage Grotesque',sans-serif;font-size:0.78rem;color:#4a3560;">
                    Déjà un compte ?
                </span>
                <span style="font-family:'Syne',sans-serif;font-size:0.78rem;
                             color:#9b6dff;font-weight:700;margin-left:6px;">
                    Clique sur Connexion ↑
                </span>
            </div>
            """, unsafe_allow_html=True)

        # ── Footer ───────────────────────────────────────────
        st.markdown("""
        <div style="text-align:center;margin-top:2rem;font-family:'Space Mono',monospace;
                    font-size:0.52rem;color:#1e1530;letter-spacing:0.12em;">
            LUMI · MASTER SISE 2025–2026
        </div>
        """, unsafe_allow_html=True)
