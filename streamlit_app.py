# ======================================================================
#  A.S.E.A. — streamlit_app.py   ·   v5.4
#  Animated threat-analysis background on every screen.
#  Hover-dropdown logo nav + rich History detail modal.
#  BACKEND LOGIC IS IDENTICAL TO STEP 7c — do not edit the marked blocks.
# ======================================================================
import time, requests, json, html, re, hashlib, unicodedata
from datetime import date
import streamlit as st
import pyrebase

# ================= Config =================
st.set_page_config(page_title="A.S.E.A. — Anti-Spam Engineered Attacks",
                   page_icon="🛡️", layout="wide",
                   initial_sidebar_state="collapsed")

API_BASE = "http://localhost:8000"          # <<< UNCHANGED (Step 7c)

# ================= Firebase =================   <<< UNCHANGED (Step 7c)
firebase_config = {
    "apiKey": st.secrets["FIREBASE_API_KEY"],
    "authDomain": st.secrets["FIREBASE_AUTH_DOMAIN"],
    "projectId": st.secrets["FIREBASE_PROJECT_ID"],
    "storageBucket": st.secrets["FIREBASE_STORAGE_BUCKET"],
    "messagingSenderId": st.secrets["FIREBASE_SENDER_ID"],
    "appId": st.secrets["FIREBASE_APP_ID"],
    "databaseURL": st.secrets.get("FIREBASE_DATABASE_URL", ""),
}
firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()

# ================= Session state =================
ss = st.session_state
ss.setdefault("user", None)          # signed-in email
ss.setdefault("name", "")            # display name
ss.setdefault("since", "")           # member since (YYYY-MM-DD)
ss.setdefault("names", {})           # email -> name captured at registration
ss.setdefault("history", [])         # recent checks
ss.setdefault("page", "Dashboard")   # plain value (nav is buttons, not a widget)
ss.setdefault("hist_filter", "All")
ss.setdefault("numcache", {})        # number -> /verify-number response
ss.setdefault("chart_view", "Bars")  # Bars | Pie chart
ss.setdefault("vt_shot_sig", "")     # v5.0: hash of the last OCR'd screenshot
ss.setdefault("vt_ocr_raw", "")      # v5.0: raw OCR output, for review
ss.setdefault("vt_ocr_err", "")      # v5.0: OCR failure message, if any
ss.setdefault("vt_sender_val", "")   # v5.1: mirror of the Contact Number box
ss.setdefault("vt_body_val", "")     # v5.1: mirror of the Message box
ss.setdefault("vt_nonce", 0)         # v5.1: bumped to rebuild the OCR widgets

# ======================================================================
#  STYLING  (non f-string: CSS braces must stay literal)
# ======================================================================
CSS = """
#MainMenu {visibility:hidden;}
header[data-testid="stHeader"] {display:none;}
[data-testid="stToolbar"] {display:none;}
footer {visibility:hidden;}

:root{
  --ink:#1b2030; --muted:#6b7280; --line:rgba(150,165,195,.28);
  --card:rgba(255,255,255,.34); --card-2:rgba(255,255,255,.20);
  --page-bg:#eef2fa;
  /* ---- frosted glass ----
     Low alpha + heavy blur is what reads as real frost. High alpha
     (the old .72) hides the backdrop, leaving nothing to blur. */
  --glass-blur:26px; --glass-sat:185%;
  --glass-edge:rgba(255,255,255,.62);
  --glass-top:inset 0 1px 0 rgba(255,255,255,.78);
  --glass-shadow:0 10px 34px rgba(20,28,50,.16);
  --glass-sheen:rgba(255,255,255,.30);
  --footer-glass:rgba(33,40,54,.52);
  --accent:#3b5bdb; --accent-2:#7048e8; --accent-soft:rgba(59,91,219,.10);
  --danger:#e03131; --warn:#f08c00; --caution:#f59f00; --safe:#2f9e44;
  --footer:#212836; --footer-ink:#e8ecf3; --footer-muted:#9aa4b6;
  --shadow:0 8px 30px rgba(20,28,50,.10);
  --shadow-hov:0 18px 44px rgba(20,28,50,.20);
  --radius:18px;
}
@media (prefers-color-scheme: dark){
  :root{
    --ink:#e9edf5; --muted:#9aa4b6; --line:rgba(140,160,200,.22);
    --card:rgba(22,28,40,.38); --card-2:rgba(22,28,40,.24);
    --page-bg:#080b12;
    --glass-edge:rgba(255,255,255,.16);
    --glass-top:inset 0 1px 0 rgba(255,255,255,.13);
    --glass-shadow:0 10px 34px rgba(0,0,0,.48);
    --glass-sheen:rgba(255,255,255,.09);
    --footer-glass:rgba(12,16,26,.52);
    --accent:#5c7cfa; --accent-2:#9775fa; --accent-soft:rgba(92,124,250,.14);
  }
}

/* ---- let the animated layer show through Streamlit's chrome ---- */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"]{
  background:transparent !important;
}
.block-container{padding-top:1.1rem; padding-bottom:0; max-width:1180px;}
html, body{color:var(--ink);}

/* ==================================================================
   ANIMATED BACKGROUND — v2.1
   Own compositor layer + negative delays, so a Streamlit rerun can
   never stall or restart the motion.
   ================================================================== */
.asea-bg{
  position:fixed; inset:0; z-index:-1; overflow:hidden;
  background:var(--page-bg);
  --boost:.32;                   /* inner pages: bright enough to read
                                    through 26px of frost. Login sets 1. */
  pointer-events:none;
  contain:layout paint;          /* wall it off from the app's layout/paint */
  transform:translateZ(0);       /* promote to its own GPU layer */
}
.asea-bg>*{will-change:transform,opacity;backface-visibility:hidden}

/* aurora — no filter:blur() (that was the expensive part); the soft
   edge now comes from the gradient stops themselves. */
.asea-bg .aurora{
  position:absolute; border-radius:50%;
  opacity:calc(.30 + var(--boost,0) * .26);
  transform:translateZ(0);
}
.asea-bg .a1{width:64vw;height:64vw;left:-20vw;top:-24vw;
  background:radial-gradient(circle closest-side,var(--accent) 0%,
             rgba(92,124,250,.34) 40%,rgba(92,124,250,.10) 66%,transparent 82%);
  animation:drift1 26s ease-in-out infinite; animation-delay:-11s}
.asea-bg .a2{width:58vw;height:58vw;right:-18vw;top:4vh;
  background:radial-gradient(circle closest-side,var(--accent-2) 0%,
             rgba(151,117,250,.32) 40%,rgba(151,117,250,.09) 66%,transparent 82%);
  animation:drift2 31s ease-in-out infinite; animation-delay:-19s}
.asea-bg .a3{width:56vw;height:56vw;left:18vw;bottom:-26vw;
  background:radial-gradient(circle closest-side,#22b8cf 0%,
             rgba(34,184,207,.28) 40%,rgba(34,184,207,.08) 66%,transparent 82%);
  animation:drift3 36s ease-in-out infinite; animation-delay:-7s}
@keyframes drift1{0%,100%{transform:translate3d(0,0,0) scale(1)}
  50%{transform:translate3d(9vw,7vh,0) scale(1.14)}}
@keyframes drift2{0%,100%{transform:translate3d(0,0,0) scale(1.08)}
  50%{transform:translate3d(-8vw,10vh,0) scale(.92)}}
@keyframes drift3{0%,100%{transform:translate3d(0,0,0) scale(1)}
  50%{transform:translate3d(-11vw,-8vh,0) scale(1.18)}}

/* moving data grid */
.asea-bg .grid{
  position:absolute; inset:-70px;
  opacity:calc(.55 + var(--boost,0) * .35);
  background-image:linear-gradient(rgba(120,145,200,.16) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(120,145,200,.16) 1px,transparent 1px);
  background-size:56px 56px;
  animation:pan 24s linear infinite; animation-delay:-13s;
  mask-image:radial-gradient(ellipse at 50% 40%,#000 20%,transparent 78%);
  -webkit-mask-image:radial-gradient(ellipse at 50% 40%,#000 20%,transparent 78%);
}
@keyframes pan{to{transform:translate3d(56px,56px,0)}}

/* classifier scan beam — animates transform, never top/left */
.asea-bg .scan{
  position:absolute; left:0; right:0; height:170px; top:0;
  opacity:calc(.6 + var(--boost,0) * .4);
  background:linear-gradient(180deg,transparent,rgba(92,124,250,.16) 45%,
             rgba(150,190,255,.55) 50%,rgba(92,124,250,.16) 55%,transparent);
  animation:sweep 7.5s cubic-bezier(.6,0,.4,1) infinite; animation-delay:-3s;
}
@keyframes sweep{
  0%{transform:translate3d(0,-170px,0);opacity:0}
  8%{opacity:1} 92%{opacity:1}
  100%{transform:translate3d(0,100vh,0);opacity:0}}

/* radar */
.asea-bg .radar{
  position:absolute; right:5vw; bottom:7vh; width:270px; height:270px;
  border-radius:50%; opacity:calc(.28 + var(--boost,0) * .18);
  background:conic-gradient(from 0deg,rgba(92,124,250,.45),transparent 22%);
  animation:spin 5.5s linear infinite; animation-delay:-2s;
}
.asea-bg .ping{
  position:absolute; right:5vw; bottom:7vh; width:270px; height:270px;
  border-radius:50%; border:1px solid rgba(120,150,230,.35);
  animation:ping 4.5s ease-out infinite; animation-delay:-1.5s;
}
.asea-bg .ping.p2{animation-delay:-3.75s}
@keyframes spin{to{transform:rotate3d(0,0,1,360deg)}}
@keyframes ping{0%{transform:scale(.25);opacity:.85}100%{transform:scale(1.15);opacity:0}}

/* floating SMS bubbles */
.asea-bg .bub{
  position:absolute; bottom:-90px;
  width:74px; height:50px; border-radius:16px;
  opacity:calc(.6 + var(--boost,0) * .4);
  background:rgba(140,170,255,.16);
  border:1px solid rgba(140,170,255,.30);
  animation:rise 20s linear infinite;
}
.asea-bg .bub:after{
  content:""; position:absolute; left:14px; bottom:-9px;
  border:9px solid transparent; border-top-color:rgba(140,170,255,.30);
}
.asea-bg .bub i{
  position:absolute; left:12px; height:5px; border-radius:3px;
  background:rgba(160,190,255,.42);
}
.asea-bg .bub i:nth-child(1){top:13px;width:46px}
.asea-bg .bub i:nth-child(2){top:24px;width:34px}
.asea-bg .bub i:nth-child(3){top:35px;width:22px}
.asea-bg .b1{left:6%;  animation-duration:21s; animation-delay:-4s}
.asea-bg .b2{left:23%; animation-duration:27s; animation-delay:-17s}
.asea-bg .b3{left:41%; animation-duration:18s; animation-delay:-9s}
.asea-bg .b4{left:62%; animation-duration:30s; animation-delay:-23s}
.asea-bg .b5{left:78%; animation-duration:23s; animation-delay:-12s}
.asea-bg .b6{left:90%; animation-duration:26s; animation-delay:-2s}
@keyframes rise{
  0%{transform:translate3d(0,0,0) rotate(-4deg);opacity:0}
  10%{opacity:.9} 90%{opacity:.9}
  100%{transform:translate3d(0,-116vh,0) rotate(5deg);opacity:0}}

/* drifting scam tokens */
.asea-bg .tok{
  position:absolute; left:0; white-space:nowrap;
  font-family:"SFMono-Regular","Menlo","Consolas",monospace;
  font-size:12.5px; letter-spacing:.4px;
  padding:5px 12px; border-radius:999px;
  opacity:calc(.55 + var(--boost,0) * .35);
  color:rgba(120,150,225,.95);
  background:rgba(120,150,230,.10);
  border:1px solid rgba(120,150,230,.26);
  animation:slide 28s linear infinite;
}
.asea-bg .t1{top:14%; animation-duration:30s; animation-delay:-6s}
.asea-bg .t2{top:27%; animation-duration:38s; animation-delay:-25s}
.asea-bg .t3{top:41%; animation-duration:26s; animation-delay:-14s}
.asea-bg .t4{top:56%; animation-duration:34s; animation-delay:-31s}
.asea-bg .t5{top:69%; animation-duration:29s; animation-delay:-3s}
.asea-bg .t6{top:82%; animation-duration:41s; animation-delay:-20s}
.asea-bg .t7{top:91%; animation-duration:33s; animation-delay:-11s}
@keyframes slide{
  0%{transform:translate3d(-40vw,0,0);opacity:0}
  8%{opacity:1} 92%{opacity:1}
  100%{transform:translate3d(112vw,0,0);opacity:0}}

/* verdict ticker */
.asea-bg .vd{
  position:absolute; font-size:10.5px; font-weight:800; letter-spacing:1.4px;
  padding:3px 9px; border-radius:6px; opacity:0;
  animation:blip 9s ease-in-out infinite;
}
.asea-bg .vd.spam{color:#ff6b6b;background:rgba(224,49,49,.12);
  border:1px solid rgba(224,49,49,.34)}
.asea-bg .vd.ham{color:#51cf66;background:rgba(47,158,68,.12);
  border:1px solid rgba(47,158,68,.34)}
.asea-bg .v1{top:20%;left:12%;animation-delay:-1s}
.asea-bg .v2{top:48%;left:71%;animation-delay:-4s}
.asea-bg .v3{top:74%;left:29%;animation-delay:-6.5s}
.asea-bg .v4{top:33%;left:52%;animation-delay:-8s}
@keyframes blip{0%,72%,100%{opacity:0;transform:scale(.8)}
  78%,92%{opacity:.95;transform:scale(1)}}

/* floating shield — strong on login, a whisper elsewhere */
.asea-bg .shield{
  position:absolute; left:50%; top:16%;
  font-size:120px; opacity:calc(.025 + var(--boost,0) * .075);
  animation:floaty 8s ease-in-out infinite; animation-delay:-2s;
}
@keyframes floaty{0%,100%{transform:translate3d(-50%,0,0)}
  50%{transform:translate3d(-50%,-22px,0)}}

@media (prefers-reduced-motion: reduce){
  .asea-bg *{animation:none !important}
  *{animation:none !important; transition:none !important}
}

/* ==================================================================
   FOREGROUND / GLASS UI
   ================================================================== */
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
@keyframes popIn{from{opacity:0;transform:scale(.94)}to{opacity:1;transform:scale(1)}}
@keyframes grow{from{width:0}}
@keyframes shift{0%{background-position:0% 50%}100%{background-position:200% 50%}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(224,49,49,.45)}
  70%{box-shadow:0 0 0 12px rgba(224,49,49,0)}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-9px)}}

.hero{text-align:center;padding:14px 16px 6px;animation:fadeUp .6s ease both}
/* v4.8.5 — TRACKING CENTRING FIX. letter-spacing is added after the
   LAST character as well, so a centred line's box is one full tracking
   step wider than the glyphs and the text sits half a step left of true
   centre. On A.S.E.A. that is 2.5px of a 5px step at 52px type — small,
   but visible against the tagline and the page title beneath it.
   text-indent pushes the line back by exactly half the tracking, which
   is the precise compensation. */
.hero .tagline{font-size:11px;letter-spacing:3px;text-transform:uppercase;
  text-indent:1.5px;
  color:var(--muted);margin-bottom:8px}
.hero .brand{font-size:52px;font-weight:800;letter-spacing:5px;margin:0;
  text-indent:2.5px;  /* v4.9: back to the EXACT compensation. letter-spacing:5px
                         is also added after the last glyph, so a centred line's box
                         is 5px wider than the glyphs and the wordmark sits 2.5px left
                         of true centre. Half the tracking is the precise fix; the old
                         7px "by eye" nudge overshot 4.5px to the RIGHT. */
  background:linear-gradient(100deg,var(--accent),var(--accent-2),#22b8cf,var(--accent));
  background-size:200% auto; -webkit-background-clip:text; background-clip:text;
  -webkit-text-fill-color:transparent; animation:shift 7s linear infinite}
.hero .ptitle{margin:14px 0 4px;font-size:20px;font-weight:650;color:var(--ink)}
.hero .psub{color:var(--muted);font-size:13.5px;margin:0}

.card{
  position:relative; overflow:hidden;
  border:1px solid var(--glass-edge); background:var(--card);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  color:var(--ink); border-radius:var(--radius); padding:20px 22px;
  margin-bottom:16px;
  box-shadow:var(--glass-shadow), var(--glass-top);
  transition:transform .22s ease, box-shadow .22s ease,
             -webkit-backdrop-filter .25s ease, backdrop-filter .25s ease;
  animation:fadeUp .55s ease both;
}
/* diagonal sheen — light catching the edge of real glass.
   The gradient is drawn at 250% of the card so there is room for it to
   TRAVEL. On hover the motion layer slides background-position to the
   far corner over ~1.8s, which reads as light slowly moving across
   glass rather than a highlight flashing past. */
.card:before{
  content:""; position:absolute; inset:0; pointer-events:none; z-index:0;
  background:linear-gradient(135deg,var(--glass-sheen) 0%,
             rgba(255,255,255,.05) 34%,transparent 62%);
  background-size:250% 250%; background-position:0% 0%;
  transition:background-position 1.8s cubic-bezier(.25,.6,.2,1);
}
.card>*{position:relative; z-index:1}
.card:hover{
  transform:translateY(-3px);
  box-shadow:var(--shadow-hov), var(--glass-top);
  -webkit-backdrop-filter:blur(15px) saturate(210%);
  backdrop-filter:blur(15px) saturate(210%);   /* clears as you lean in */
}
.card.flat:hover{transform:none;
  box-shadow:var(--glass-shadow), var(--glass-top)}

.kpi{text-align:center;padding:20px 12px}
.kpi .ico{font-size:22px;opacity:.85}
.kpi .num{font-size:32px;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(120deg,var(--accent),var(--accent-2));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.kpi .lbl{color:var(--muted);font-size:10.5px;text-transform:uppercase;
  letter-spacing:1.4px;margin-top:4px}

.sec-title{margin:0 0 12px;font-size:11px;color:var(--muted);
  text-transform:uppercase;letter-spacing:1.6px;font-weight:700}
.barlabel{font-size:13px;display:flex;justify-content:space-between;
  color:var(--ink);margin-bottom:5px}
.bar{height:9px;background:var(--accent-soft);border-radius:99px;
  overflow:hidden;margin-bottom:14px}
.bar>span{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--accent),var(--accent-2));
  animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}

.badge{display:inline-block;padding:5px 13px;border-radius:99px;
  font-size:11.5px;font-weight:800;letter-spacing:1.1px;animation:popIn .35s ease both}
.badge.danger{background:rgba(224,49,49,.14);color:var(--danger);
  border:1px solid rgba(224,49,49,.35);animation:popIn .35s ease both,pulse 2s infinite}
.badge.warn{background:rgba(240,140,0,.14);color:var(--warn);border:1px solid rgba(240,140,0,.35)}
.badge.caution{background:rgba(245,159,0,.13);color:var(--caution);border:1px solid rgba(245,159,0,.32)}
.badge.safe{background:rgba(47,158,68,.14);color:var(--safe);border:1px solid rgba(47,158,68,.35)}
.badge.neutral{background:var(--accent-soft);color:var(--accent);border:1px solid var(--line)}

.meter{height:11px;border-radius:99px;background:var(--accent-soft);overflow:hidden;margin:8px 0}
.meter>span{display:block;height:100%;border-radius:99px;
  animation:grow 1.2s cubic-bezier(.2,.8,.2,1) both}

.msgbox{background:var(--card-2);border:1px dashed var(--glass-edge);
  -webkit-backdrop-filter:blur(18px) saturate(160%);
  backdrop-filter:blur(18px) saturate(160%);
  border-radius:12px;
  padding:14px 16px;font-size:14px;line-height:1.65;white-space:pre-wrap;
  word-break:break-word;color:var(--ink);max-height:260px;overflow:auto}

/* flagged-token chips in the history modal */
.tokchips{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 4px}
.tokchip{display:inline-block;padding:6px 12px;border-radius:999px;
  font-family:"SFMono-Regular",Menlo,Consolas,monospace;font-size:12.5px;
  background:rgba(224,49,49,.10);color:#e03131;
  border:1px solid rgba(224,49,49,.30);animation:popIn .3s ease both}
.tokchip.safe{background:rgba(47,158,68,.10);color:#2f9e44;
  border-color:rgba(47,158,68,.30)}
.tokchip .w{font-weight:800;letter-spacing:.3px}

.numcard{display:flex;flex-wrap:wrap;gap:14px;margin-top:4px}
.numcard .nb{flex:1;min-width:150px;border:1px solid var(--glass-edge);
  border-radius:14px;padding:14px 16px;background:var(--card-2);
  -webkit-backdrop-filter:blur(18px) saturate(170%);
  backdrop-filter:blur(18px) saturate(170%);
  box-shadow:var(--glass-top);
  animation:popIn .35s ease both}
.numcard .nb .t{font-size:10px;text-transform:uppercase;letter-spacing:1.3px;
  color:var(--muted);font-weight:700;margin-bottom:6px}
.numcard .nb .v{font-size:19px;font-weight:800;color:var(--ink);
  font-family:"SFMono-Regular",Menlo,Consolas,monospace;word-break:break-all}
.numcard .nb .v.small{font-size:15px;font-family:inherit}

.asea-table{width:100%;border-collapse:collapse;margin-top:6px}
.asea-table th,.asea-table td{border-bottom:1px solid var(--line);
  padding:10px 12px;text-align:left;font-size:13px;color:var(--ink)}
.asea-table th{font-size:10.5px;text-transform:uppercase;letter-spacing:1.2px;
  color:var(--muted);font-weight:700}
.asea-table tr:last-child td{border-bottom:none}

.hrow{display:flex;align-items:center;gap:14px}
.hrow .when{font-size:11.5px;color:var(--muted);min-width:112px;
  font-family:"SFMono-Regular",Menlo,Consolas,monospace}
.hrow .snip{flex:1;font-size:13.5px;color:var(--ink);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}

.empty{text-align:center;padding:34px 16px;color:var(--muted)}
.empty .big{font-size:42px;opacity:.5;display:block;margin-bottom:8px;
  animation:bob 4s ease-in-out infinite}

/* inputs + buttons */
.stTextInput input,.stTextArea textarea{
  border:1px solid var(--glass-edge) !important;border-radius:12px !important;
  background:var(--card-2) !important;
  -webkit-backdrop-filter:blur(18px) saturate(160%) !important;
  backdrop-filter:blur(18px) saturate(160%) !important;
  transition:border-color .2s ease,box-shadow .2s ease !important;
}
.stTextInput input:focus,.stTextArea textarea:focus{
  border-color:var(--accent) !important;
  box-shadow:0 0 0 4px var(--accent-soft) !important;
}
.stButton>button{
  border-radius:12px;font-weight:650;letter-spacing:.3px;padding:9px 20px;
  border:1px solid var(--glass-edge);background:var(--card);color:var(--ink);
  -webkit-backdrop-filter:blur(20px) saturate(175%);
  backdrop-filter:blur(20px) saturate(175%);
  box-shadow:var(--glass-top);
  transition:transform .18s ease,box-shadow .18s ease,background .18s ease;
}
.stButton>button:hover{transform:translateY(-2px);box-shadow:var(--shadow-hov);
  border-color:var(--accent);color:var(--accent)}
.stButton>button[kind="primary"],
.stButton>button[data-testid="baseButton-primary"]{
  background:linear-gradient(120deg,var(--accent),var(--accent-2),var(--accent));
  background-size:200% auto;color:#fff !important;border:none;
  animation:shift 5s linear infinite;
}
.stButton>button[kind="primary"]:hover{color:#fff !important}
.stFormSubmitButton>button{
  border-radius:12px;font-weight:700;letter-spacing:.6px;
  background:linear-gradient(120deg,var(--accent),var(--accent-2),var(--accent));
  background-size:200% auto;color:#fff;border:none;padding:11px 20px;
  animation:shift 5s linear infinite;
}
.stFormSubmitButton>button:hover{transform:translateY(-2px);
  box-shadow:var(--shadow-hov);color:#fff}
[data-testid="stForm"]{border:1px solid var(--glass-edge);
  border-radius:var(--radius); background:var(--card);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  box-shadow:var(--glass-shadow), var(--glass-top); padding:22px}
.stTabs [data-baseweb="tab-list"]{gap:6px;justify-content:center}
.stTabs [data-baseweb="tab"]{border-radius:10px;padding:6px 18px;font-weight:650}

/* ==================================================================
   HOVER-DROPDOWN LOGO NAV
   The marker div is the first child of its container; the five page
   buttons are the siblings after it. Hovering the container (which
   includes the absolutely-positioned menu, since CSS :hover counts
   descendants) reveals them.
   ================================================================== */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker){
  position:relative; z-index:70;
}
.asea-menu-marker{
  display:inline-flex; align-items:center; gap:12px; cursor:pointer;
  padding:9px 16px; border-radius:14px; border:1px solid var(--line);
  background:var(--card); box-shadow:var(--glass-shadow), var(--glass-top);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  transition:box-shadow .2s ease, transform .2s ease;
}
.asea-menu-marker .logo{
  font-size:23px; font-weight:800; letter-spacing:3.5px; line-height:1;
  background:linear-gradient(100deg,var(--accent),var(--accent-2),#22b8cf,var(--accent));
  background-size:200% auto; -webkit-background-clip:text; background-clip:text;
  -webkit-text-fill-color:transparent; animation:shift 7s linear infinite;
}
.asea-menu-marker .caret{
  color:var(--muted); font-size:12px; line-height:1;
  transition:transform .28s cubic-bezier(.2,.8,.2,1);
}
.asea-menu-marker .cur{
  font-size:12.5px; color:var(--muted); font-weight:600;
  border-left:1px solid var(--line); padding-left:12px;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  .asea-menu-marker{box-shadow:var(--shadow-hov); transform:translateY(-1px)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  .asea-menu-marker .caret{transform:rotate(180deg)}

/* every element after the marker = a dropdown row */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:not(:first-child){
  position:absolute; left:0; width:240px;
  opacity:0; pointer-events:none;
  transform:translateY(-8px) scale(.98);
  transition:opacity .2s ease, transform .2s cubic-bezier(.2,.8,.2,1);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:nth-child(2){top:100%; padding-top:8px}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:nth-child(3){top:calc(100% + 52px)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:nth-child(4){top:calc(100% + 96px)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:nth-child(5){top:calc(100% + 140px)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:nth-child(6){top:calc(100% + 184px)}

[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  > [data-testid="stElementContainer"]:not(:first-child){
  opacity:1; pointer-events:auto; transform:none;
}
/* stagger the reveal */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  > [data-testid="stElementContainer"]:nth-child(2){transition-delay:.02s}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  > [data-testid="stElementContainer"]:nth-child(3){transition-delay:.05s}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  > [data-testid="stElementContainer"]:nth-child(4){transition-delay:.08s}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  > [data-testid="stElementContainer"]:nth-child(5){transition-delay:.11s}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker):hover
  > [data-testid="stElementContainer"]:nth-child(6){transition-delay:.14s}

/* dropdown row styling — left aligned, no icons */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:not(:first-child) .stButton>button{
  justify-content:flex-start; text-align:left; padding:10px 16px;
  border-radius:12px; font-weight:600; letter-spacing:.2px;
  background:var(--card); border:1px solid var(--glass-edge);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  box-shadow:var(--glass-shadow), var(--glass-top);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-menu-marker)
  > [data-testid="stElementContainer"]:not(:first-child) .stButton>button:hover{
  transform:translateX(4px); border-color:var(--accent);
  background:var(--accent-soft);
}

/* ==================================================================
   RED LOG OUT BUTTON
   ================================================================== */
/* ---- the user glass chip + its hover dropdown (top-right) ----
   Same construction as the A.S.E.A. logo menu: an invisible marker is
   the FIRST child of the container, and every sibling after it becomes
   an absolutely-positioned dropdown row.

   Two deliberate details:
   1. The row selector is "> *:not(:first-child)", NOT
      "> [data-testid=stElementContainer]". LOG OUT sits inside its own
      nested st.container() so it can keep its own marker and therefore
      its untouched red styling, and a nested container renders as a
      different wrapper element than a plain element container.
   2. The row STYLING rule below excludes anything containing
      .asea-logout-marker. Without that guard it would out-specify the
      red gradient rules further down and repaint LOG OUT as glass. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker){
  position:relative; z-index:69;
}
.asea-user-marker{
  display:inline-flex; align-items:center; gap:14px; cursor:pointer;
  text-align:left; padding:8px 16px; border-radius:14px;
  border:1px solid var(--line); background:var(--card);
  box-shadow:var(--glass-shadow), var(--glass-top);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  transition:box-shadow .2s ease, transform .2s ease;
}
.asea-user-marker .who{line-height:1.3}
.asea-user-marker .nm{font-weight:700;font-size:13.5px;color:var(--ink)}
.asea-user-marker .em{color:var(--muted);font-size:11.5px}
.asea-user-marker .caret{
  color:var(--muted); font-size:12px; line-height:1;
  transition:transform .28s cubic-bezier(.2,.8,.2,1);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker):hover
  .asea-user-marker{box-shadow:var(--shadow-hov); transform:translateY(-1px)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker):hover
  .asea-user-marker .caret{transform:rotate(180deg)}

/* the two dropdown rows: Account, then LOG OUT */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker)
  > *:not(:first-child){
  position:absolute; right:0; width:220px;
  z-index:2;                     /* MUST stay above the hover bridge */
  opacity:0; pointer-events:none;
  transform:translateY(-8px) scale(.98);
  transition:opacity .2s ease, transform .2s cubic-bezier(.2,.8,.2,1);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker)
  > *:nth-child(2){top:100%; padding-top:8px}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker)
  > *:nth-child(3){top:calc(100% + 72px)}   /* v4.7: was 50px — LOG OUT
                                              was overlapping and clipping
                                              the bottom of the Account row */
/* HOVER BRIDGE — fixes "the menu vanishes while I am moving onto it".
   The chip's own box is only as tall as the chip; the rows are
   absolutely positioned, so they are out of flow. Any pixel of dead
   space between the chip and a row, or between the two rows, is
   outside the container entirely — the pointer crossing it fires
   mouseleave and the menu collapses before you arrive. This invisible
   pad covers the whole dropwn area so the pointer never leaves. It is
   click-through until the menu is actually open, and the rows paint
   above it, so it can never swallow a click. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker):after{
  content:""; position:absolute; right:0; top:100%;
  width:220px; height:160px; pointer-events:none;   /* v4.7: taller, so it
     still covers the whole menu now that LOG OUT sits 72px down */
  /* BUG FIXED IN v3.9 — do not remove this z-index.
     ::after generates a box AFTER every real child, so as another
     positioned element with z-index:auto it painted ON TOP of the
     Account and LOG OUT rows and swallowed every click. The rows are
     z-index:2, this pad is z-index:1, so it can only ever sit behind
     them while still catching the dead space around them. */
  z-index:1;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker):hover:after{
  pointer-events:auto;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker):hover
  > *:not(:first-child){opacity:1; pointer-events:auto; transform:none}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker):hover
  > *:nth-child(2){transition-delay:.02s}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker):hover
  > *:nth-child(3){transition-delay:.05s}

/* Account row — glass, left-aligned. The :not(:has(...)) guard keeps
   every one of these declarations away from LOG OUT. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker)
  > *:not(:first-child):not(:has(.asea-logout-marker)) .stButton>button{
  justify-content:flex-start; text-align:left; padding:10px 16px;
  border-radius:12px; font-weight:600; letter-spacing:.2px;
  background:var(--card); border:1px solid var(--glass-edge);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  box-shadow:var(--glass-shadow), var(--glass-top);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker)
  > *:not(:first-child):not(:has(.asea-logout-marker)) .stButton>button:hover{
  transform:translateX(-4px); border-color:var(--accent);
  background:var(--accent-soft);
}
/* collapse the nested LOG OUT container's own marker row so the button
   is not pushed down by an empty element */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-user-marker)
  [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-logout-marker)
  > [data-testid="stElementContainer"]:first-child{display:none}

/* ==================================================================
   CHART-TYPE SWITCHER — the v4.2 caret, opening DOWN on HOVER
   Same mechanism as the A.S.E.A. logo menu and the user chip.

   The trigger is the v4.2 caret, unchanged: a 38×28 glass square
   holding one ▾, to the LEFT of the heading. Hovering it now slides
   the options down instead of needing a click.

   WHY THE PREVIOUS TWO ATTEMPTS BROKE — both times the options ended
   up as ordinary stacked buttons in a 60px column with their labels
   wrapped vertically, because the CSS silently matched NOTHING:
     v3.8  hid the rows with  > *:not(:first-child)  — the marker was
           not the container's first child once nested in the panel's
           column, so the rule never applied.
     v4.3  found the rows by  .st-key-cv_bars / .st-key-cv_pie  —
           Streamlit only stamps widget keys as CSS classes on newer
           versions, so on this build those classes do not exist.

   THE RULE THIS VERSION FOLLOWS: hook only on things this file itself
   puts in the DOM (.asea-chartmenu-marker) or that Streamlit has
   shipped for years (.stButton). No widget-key classes, no ordinals
   counted from the top, no > direct-child selectors against
   Streamlit's internals.

     v4.4  anchored everything on [data-testid="stColumn"] — which is
           NOT what the two working menus use. The logo menu and the
           user chip anchor on [data-testid="stVerticalBlock"], the
           column's inner block. On this build the stColumn test id
           evidently is not there, so again: nothing matched.

   So v4.5 is a literal copy of the logo menu's anchor, which is proven
   to work in this very file:
     [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .MARKER)
   The direct child is deliberate here: with a descendant :has() the
   panel and the page block would match too, and hovering anywhere in
   the card would open the menu.

   How the rows are found: TWO equivalent selector families are
   written out below on purpose, belt and braces. The first picks any
   element container holding a button (so the marker, which holds
   none, is never caught) and reaches the second row with the sibling
   combinator ~. The second is the logo menu's exact :not(:first-child)
   + nth-child form. If either family fails on a future Streamlit, the
   other still styles and positions the rows.

   Glass here is glass-ON-glass: translucent tint + sheen + bright
   edge with only a LIGHT blur. A heavy nested blur just re-blurs the
   panel's already-blurred output and reads as muddy grey.
   ================================================================== */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker){
  position:relative; z-index:72;
  overflow:visible !important;   /* v4.6: rows must be able to escape */
}
/* v4.6 — THE CLIPPING FIX. In v4.5 the CSS finally matched, but the
   caret lived in a 60px column, and an absolutely-positioned row can
   never escape an ancestor that clips: the 176px rows were sliced off
   at the column edge, showing "Bar" and "Pie c". The menu now lives in
   a FULL-WIDTH container instead of a narrow column, and every
   ancestor around it is forced to overflow:visible as well. */
[data-testid="stVerticalBlockBorderWrapper"]:has(.asea-chartmenu-marker),
[data-testid="stVerticalBlock"]:has(.asea-chartmenu-marker){
  overflow:visible !important;
}

/* the caret and the heading share one flex row, so no column split is
   needed for the caret to sit to the LEFT of the title */
.asea-chartmenu-row{
  display:flex; align-items:center; gap:10px; margin:0 0 2px;
}
.asea-chartmenu-row .sec-title{margin:0}

/* the trigger — the v4.2 caret, identical in look */
.asea-chartmenu-marker{
  position:relative;   /* v4.8: anchors the hover bridge under the arrow */
  display:inline-flex; align-items:center; justify-content:center;
  cursor:pointer; width:38px; height:28px; border-radius:10px;
  background:linear-gradient(135deg, var(--glass-sheen),
             rgba(255,255,255,0) 72%), var(--card);
  -webkit-backdrop-filter:blur(10px) saturate(160%);
  backdrop-filter:blur(10px) saturate(160%);
  border:1px solid var(--glass-edge);
  box-shadow:var(--glass-top), 0 4px 14px rgba(20,28,50,.10);
  transition:transform .22s cubic-bezier(.2,.8,.2,1), border-color .2s ease,
             box-shadow .2s ease, backdrop-filter .2s ease;
}
.asea-chartmenu-marker .caret{
  font-size:12px; font-weight:800; line-height:1; color:var(--ink);
  transition:transform .3s cubic-bezier(.2,.8,.2,1), color .2s ease;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker:hover)
  .asea-chartmenu-marker{
  transform:translateY(-1px); border-color:var(--accent);
  box-shadow:var(--glass-top), var(--shadow-hov);
  -webkit-backdrop-filter:blur(15px) saturate(210%);
  backdrop-filter:blur(15px) saturate(210%);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker:hover)
  .asea-chartmenu-marker .caret{
  transform:rotate(180deg); color:var(--accent);
}

/* ---- rows, family A: "the containers holding a button" ----------- */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  > [data-testid="stElementContainer"]:has(.stButton){
  position:absolute; left:0; top:calc(100% + 8px); width:176px; z-index:2;
  opacity:0; pointer-events:none;
  transform:translateY(-10px) scale(.96);
  transition:opacity .22s ease, transform .3s cubic-bezier(.2,.9,.25,1);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  > [data-testid="stElementContainer"]:has(.stButton)
  ~ [data-testid="stElementContainer"]:has(.stButton){
  top:calc(100% + 56px);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker:hover)
  > [data-testid="stElementContainer"]:has(.stButton){
  opacity:1; pointer-events:auto; transform:none; transition-delay:.03s;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker:hover)
  > [data-testid="stElementContainer"]:has(.stButton)
  ~ [data-testid="stElementContainer"]:has(.stButton){
  transition-delay:.09s;
}

/* ---- rows, family B: the logo menu's exact form, as a fallback --- */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  > [data-testid="stElementContainer"]:not(:first-child){
  position:absolute; left:0; width:176px; z-index:2;
  opacity:0; pointer-events:none;
  transform:translateY(-10px) scale(.96);
  transition:opacity .22s ease, transform .3s cubic-bezier(.2,.9,.25,1);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  > [data-testid="stElementContainer"]:nth-child(2){top:calc(100% + 8px)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  > [data-testid="stElementContainer"]:nth-child(3){top:calc(100% + 56px)}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker:hover)
  > [data-testid="stElementContainer"]:not(:first-child){
  opacity:1; pointer-events:auto; transform:none;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker:hover)
  > [data-testid="stElementContainer"]:nth-child(2){transition-delay:.03s}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker:hover)
  > [data-testid="stElementContainer"]:nth-child(3){transition-delay:.09s}

/* hover bridge — v4.8: this is now a pseudo-element of the ARROW, not
   of the container. Hovering an ::after counts as hovering the element
   it belongs to, so the pointer can travel from the arrow down to the
   rows without the menu collapsing. On the container it would also
   re-arm the menu from anywhere along that full-width strip — which is
   precisely the bug v4.8 fixes.
   z-index:1 is MANDATORY — ::after generates its box after every real
   child, so with automatic stacking it would paint OVER the rows and
   swallow their clicks (the v3.8 chip bug). Rows are 2, this is 1. */
.asea-chartmenu-marker:after{
  content:""; position:absolute; left:0; top:100%; z-index:1;
  width:176px; height:150px; pointer-events:none;
}
.asea-chartmenu-marker:hover:after{ pointer-events:auto; }
/* v4.8.1 — the bridge must ALSO stay live while a row is hovered.
   Rows sit 8px apart, and crossing that gap the pointer is over the
   bridge, not over a row — with the bridge dead at that moment both
   open conditions went false and the menu closed before the pointer
   reached "Pie chart". Keeping it live hands the hover back to the
   arrow (a pseudo-element's hover belongs to its owner), so the chain
   arrow → bridge → Bars → bridge → Pie chart never breaks. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker):has(> [data-testid="stElementContainer"]:hover .stButton)
  .asea-chartmenu-marker:after{ pointer-events:auto; }

/* v4.8 — second open condition: keep the menu open while the pointer
   is ON a row. The rows are siblings of the arrow, not descendants, so
   .asea-chartmenu-marker:hover goes false the instant you land on one.
   This condition cannot open the menu by itself: while closed the rows
   are pointer-events:none and therefore cannot be hovered at all. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker):has(> [data-testid="stElementContainer"]:hover .stButton)
  > [data-testid="stElementContainer"]:has(.stButton),
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker):has(> [data-testid="stElementContainer"]:hover .stButton)
  > [data-testid="stElementContainer"]:not(:first-child){
  opacity:1; pointer-events:auto; transform:none;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker):has(> [data-testid="stElementContainer"]:hover .stButton)
  .asea-chartmenu-marker .caret{
  transform:rotate(180deg); color:var(--accent);
}

/* row styling — frosted glass, same language as the cards */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  > [data-testid="stElementContainer"]:not(:first-child) .stButton>button{
  justify-content:flex-start; text-align:left; padding:9px 15px;
  border-radius:12px; font-weight:600; font-size:13px; color:var(--ink);
  white-space:nowrap;
  background:linear-gradient(135deg, var(--glass-sheen),
             rgba(255,255,255,0) 72%), var(--card);
  -webkit-backdrop-filter:blur(16px) saturate(180%);
  backdrop-filter:blur(16px) saturate(180%);
  border:1px solid var(--glass-edge);
  box-shadow:var(--glass-shadow), var(--glass-top);
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  > [data-testid="stElementContainer"]:not(:first-child) .stButton>button:hover{
  transform:translateX(3px); border-color:var(--accent);
  background:var(--accent-soft);
}
/* the row matching the current view */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-chartmenu-marker)
  .stButton>button[kind="primary"]{
  background:linear-gradient(120deg,var(--accent),var(--accent-2));
  border-color:transparent; color:#fff;
  box-shadow:0 6px 18px rgba(59,91,219,.30);
}

[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-logout-marker)
  .stButton>button{
  position:relative; overflow:hidden; border:none !important;
  font-weight:800; letter-spacing:1.4px; font-size:12.5px;
  color:#fff !important; border-radius:12px;
  background:linear-gradient(120deg,#e03131,#c92a2a,#e03131);
  background-size:200% auto;
  box-shadow:0 6px 18px rgba(224,49,49,.34);
  transition:background-position .5s ease, box-shadow .28s ease,
             transform .22s cubic-bezier(.2,.8,.2,1), letter-spacing .28s ease;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-logout-marker)
  .stButton>button:hover{
  background:linear-gradient(120deg,var(--accent),var(--accent-2),#22b8cf);
  background-size:200% auto; background-position:100% 50%;
  color:#fff !important; letter-spacing:2.2px;
  transform:translateY(-3px) scale(1.02);
  box-shadow:0 14px 30px rgba(59,91,219,.42);
}
/* shimmer sweep on hover */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-logout-marker)
  .stButton>button:after{
  content:""; position:absolute; top:0; left:-120%; width:60%; height:100%;
  background:linear-gradient(100deg,transparent,rgba(255,255,255,.45),transparent);
  transform:skewX(-20deg); transition:left .55s ease;
}
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-logout-marker)
  .stButton>button:hover:after{left:130%}

/* ==================================================================
   GLASS PANEL THAT CAN HOLD LIVE WIDGETS
   .card is an HTML string, so it cannot wrap a Streamlit chart or
   popover. This styles a real st.container() the same way, anchored
   to an invisible marker div.
   ================================================================== */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-panel-marker){
  position:relative;
  border:1px solid var(--glass-edge); background:var(--card);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  border-radius:var(--radius); padding:20px 22px; margin-bottom:16px;
  box-shadow:var(--glass-shadow), var(--glass-top);
  animation:fadeUp .55s ease both;
  gap:0 !important;              /* match the old .card's tight spacing */
}
/* Spacing below the title row is handled INLINE in render_scam_chart(),
   not here. This selector needs stHorizontalBlock to be a direct child
   of the panel, but Streamlit nests the columns row inside a wrapper,
   so the rule silently missed and the margin never applied. Left at 0
   so it cannot double up with the inline value if a future Streamlit
   version does flatten the DOM. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-panel-marker)
  > [data-testid="stHorizontalBlock"]{margin-bottom:0}
/* collapse the marker's own empty container */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-panel-marker)
  > [data-testid="stElementContainer"]:first-child{display:none}

/* ---- the ▾ chart-type trigger ----
   WARNING, learned the hard way: do NOT write a bare
   [data-testid="stHorizontalBlock"]:has(.some-class) rule here.
   :has() searches ALL descendants, so it also matched the dashboard's
   OUTER two-column row (which contains this panel several levels down)
   and collapsed the entire layout, shrinking this card and squashing
   the Quick actions card beside it. Every rule below is scoped inside
   the panel marker so it can never escape. */
/* WHY THIS IS NOT SCOPED AND NOT USING ">":
   1. The chart switcher is the ONLY popover in the app, so a global
      selector is safe and removes the :has() dependency entirely.
   2. Streamlit wraps the trigger in an intermediate <div>, so an
      earlier "[data-testid='stPopover'] > button" rule matched nothing
      and the button kept its default solid look. Descendant selectors
      plus every known testid alias are used below so it cannot miss.
   3. The popover BODY is portalled to the page root by BaseWeb, so it
      is NOT a descendant of the trigger — option buttons inside the
      menu are unaffected by these rules. */
[data-testid="stPopover"] button,
[data-testid="stPopover"] [data-testid^="stBaseButton"],
[data-testid="stPopoverButton"],
.stPopover button{
  min-height:0 !important; height:28px !important;
  padding:0 9px !important; font-size:12px !important;
  min-width:36px !important;   /* label is empty; keep a tappable box */
  font-weight:800 !important; line-height:1 !important;
  border-radius:10px !important; outline:none !important;
  color:var(--ink) !important;
  /* Glass ON glass: the card already runs a backdrop-filter, and a
     second heavy blur nested inside it only re-blurs the card's own
     output, which looks muddy. A translucent tint plus the sheen and
     edge is what actually reads as frosted here. */
  background:linear-gradient(135deg, var(--glass-sheen),
                             rgba(255,255,255,0) 72%),
             var(--card) !important;
  -webkit-backdrop-filter:blur(10px) saturate(160%) !important;
  backdrop-filter:blur(10px) saturate(160%) !important;
  border:1px solid var(--glass-edge) !important;
  box-shadow:var(--glass-top), 0 4px 14px rgba(20,28,50,.10) !important;
  transition:background .2s ease, color .2s ease, border-color .2s ease,
             box-shadow .2s ease, backdrop-filter .2s ease !important;
}
/* hover sharpens the glass, exactly like .card does */
[data-testid="stPopover"] button:hover,
[data-testid="stPopover"] [data-testid^="stBaseButton"]:hover,
[data-testid="stPopoverButton"]:hover,
.stPopover button:hover{
  background:linear-gradient(135deg, var(--glass-sheen),
                             rgba(255,255,255,0) 55%),
             var(--card) !important;
  -webkit-backdrop-filter:blur(15px) saturate(210%) !important;
  backdrop-filter:blur(15px) saturate(210%) !important;
  border-color:var(--accent) !important; color:var(--accent) !important;
  box-shadow:var(--glass-top), var(--shadow-hov) !important;
  transform:none !important;
}

/* the floating menu — frosted to match the card it sits on. BaseWeb
   portals this to the page root, so it is styled globally by testid. */
[data-testid="stPopoverBody"],
[data-baseweb="popover"] [data-testid="stPopoverBody"],
[data-baseweb="popover"] > div > div{
  background:linear-gradient(135deg, var(--glass-sheen),
                             rgba(255,255,255,0) 65%),
             var(--card) !important;
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  border:1px solid var(--glass-edge) !important;
  border-radius:14px !important;
  box-shadow:var(--glass-shadow), var(--glass-top) !important;
}
[data-testid="stPopoverBody"]{padding:14px !important}
/* Streamlit's chart toolbar (fullscreen / download / copy / show data)
   floats at the chart's top-right. Guarantee it always wins the stacking
   contest against anything else inside the panel. */
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .asea-panel-marker)
  [data-testid="stElementToolbar"]{z-index:70 !important}

/* v4.8.2 — THE TOOLBAR MUST NOT VANISH WHEN YOU REACH FOR IT.
   Streamlit draws this toolbar OUTSIDE the top edge of the chart it
   belongs to (negative top offset) and reveals it from the chart's own
   hover state. The moment the pointer crosses onto the toolbar it is no
   longer over the chart, the reveal condition drops, and the toolbar
   fades out from under the cursor. These rules pin it open on its own
   hover, so the reveal no longer depends on staying over the chart.
   Scoped strictly to stElementToolbar — the chart dropdown is not
   touched by any selector here. */
/* v4.8.4 — ELEMENT TOOLBAR DISABLED, DELIBERATELY.
   Streamlit's fullscreen / download / copy / show-data toolbar is
   removed outright. Three attempts to make it usable all failed for
   reasons that are structural, not cosmetic: Streamlit reveals it from
   the CHART's hover state while positioning it outside the chart's top
   edge, so it fades exactly as the pointer arrives; a :hover-scoped
   override can never fire because there is no hover state left to
   match; and pinning it permanently visible covered the donut's ring
   labels, shifted on hover, and still refused clicks — something above
   it owns that corner of the panel.
   It carries no A.S.E.A. function: this chart is a fixed weekly
   summary, not an export surface. So it is switched off.
   TO BRING IT BACK: delete this single rule. Nothing else depends on
   it, and no .asea-chartmenu-* rule was changed for it. */
[data-testid="stElementToolbar"]{display:none !important}
[data-testid="stElementToolbarButtonContainer"]{display:none !important}
/* the buttons inside it must accept the pointer as well */
[data-testid="stElementToolbar"] *{pointer-events:auto !important}
/* keep Altair charts on the glass, not on a white plate */
[data-testid="stVegaLiteChart"], [data-testid="stVegaLiteChart"] canvas,
[data-testid="stVegaLiteChart"] svg{background:transparent !important}

/* ---- Vega hover tooltip ----
   Vega appends its tooltip to <body>, NOT inside the chart. If the chart
   unmounts while the pointer is still over it — exactly what happens when
   you slide from an arc onto the chevron and click Bars — no mouseout ever
   fires, so the node survives the rerun still flagged visible, holding its
   last datum, and falls back to 0,0 in the top-left corner.

   v2.7 killed the tooltip outright. This is the better fix: the element is
   only ever allowed to paint while a Vega chart is genuinely under the
   pointer. Move off the chart — or unmount it — and the guard hides it the
   same frame, so it can never be stranded. pointer-events:none stops the
   tooltip from sitting under the cursor and cancelling its own hover. */
#vg-tooltip-element{
  pointer-events:none !important;
  background:linear-gradient(135deg, var(--glass-sheen),
                             rgba(255,255,255,0) 65%),
             var(--card) !important;
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  border:1px solid var(--glass-edge) !important;
  border-radius:10px !important;
  box-shadow:var(--glass-shadow), var(--glass-top) !important;
  color:var(--ink) !important; font-family:inherit !important;
  font-size:12px !important; padding:8px 10px !important;
}
#vg-tooltip-element td.key{color:var(--muted) !important; font-weight:700}
#vg-tooltip-element td.value{color:var(--ink) !important; font-weight:800}
/* the guard: no hovered chart anywhere => no tooltip, ever */
body:not(:has([data-testid="stVegaLiteChart"]:hover)) #vg-tooltip-element{
  display:none !important;
}

/* footer */
/* frosted-glass footer — the animation drifts behind it, blurred */
.site-footer{position:relative; overflow:hidden;
  background:var(--footer-glass); color:var(--footer-ink);
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat));
  border:1px solid rgba(255,255,255,.15);
  padding:24px 30px 14px;font-size:12px;border-radius:var(--radius);
  margin-top:38px;animation:fadeUp .6s ease both;
  box-shadow:var(--glass-shadow), inset 0 1px 0 rgba(255,255,255,.18)}
.site-footer:before{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(135deg,rgba(255,255,255,.12) 0%,transparent 58%)}
.site-footer .frow,.site-footer .copy{position:relative;z-index:1}
.site-footer .frow{display:flex;flex-wrap:wrap;justify-content:space-between;gap:18px}
.site-footer .hashtag{font-weight:800;letter-spacing:2px;margin-top:8px;
  background:linear-gradient(100deg,#8ea2ff,#c0a6ff,#8ea2ff);background-size:200% auto;
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  animation:shift 6s linear infinite}
.site-footer .contact{line-height:1.8}
.site-footer .contact a{color:var(--footer-ink);text-decoration:underline}
.site-footer .copy{color:var(--footer-muted);font-size:10px;margin-top:18px}
.site-footer svg{width:16px;height:16px;fill:currentColor;margin-right:14px;
  transition:transform .2s ease}
.site-footer svg:hover{transform:translateY(-3px) scale(1.15)}

/* ==================================================================
   MOTION LAYER — v3.6
   Every interactive surface gets a transition and a hover animation:
   cards, all st.buttons (View / Detect / Clear / Close / nav rows /
   Quick actions), the SIGN IN and CREATE ACCOUNT submits, the Sign In
   and Register tabs, and the modal and its X.

   REMOVED in v3.6, by request: the shimmer/sweep highlight that shot
   across cards and buttons, and the whole-screen fade when moving
   between pages. Cards now move a slow sheen instead. Nothing else
   about the layout or the backend changed.

   SAFETY RULE for this whole block, learned from the v2.6 regression:
   these rules only ever touch transform, opacity, box-shadow,
   background, border-color, backdrop-filter and letter-spacing. Not
   one of them changes display, width, flex or position on a shared
   Streamlit container, so the layout cannot collapse. The
   prefers-reduced-motion block further up still overrides all of it.
   ================================================================== */
@keyframes pageIn{
  from{opacity:0; transform:translate3d(0,14px,0)}
  to{opacity:1; transform:none}}
@keyframes modalIn{
  from{opacity:0; transform:translate3d(0,18px,0) scale(.97)}
  to{opacity:1; transform:none}}
/* ---- cards: lift, sharpen, and drift the sheen slowly across ----
   No :after streak any more. The card's own sheen (.card:before)
   simply travels to the opposite corner while the pointer rests on
   it, and travels back when the pointer leaves. */
.card{transition:transform .32s cubic-bezier(.2,.8,.2,1),
                 box-shadow .32s ease, border-color .32s ease,
                 -webkit-backdrop-filter .3s ease,
                 backdrop-filter .3s ease}
.card:hover{transform:translateY(-6px) scale(1.01);
  border-color:rgba(120,150,230,.55)}
.card:hover:before{background-position:100% 100%}
/* .flat cards (Quick actions, empty states) stay completely still */
.card.flat:hover{transform:none;
  box-shadow:var(--glass-shadow), var(--glass-top)}
.card.flat:hover:before{background-position:0% 0%}

/* ---- every st.button: View, DETECT, Clear, Close, Quick actions,
        the History filters, and the nav dropdown rows ---- */
.stButton>button{
  position:relative; overflow:hidden;
  transition:transform .2s cubic-bezier(.2,.8,.2,1), box-shadow .2s ease,
             background .2s ease, border-color .2s ease, color .2s ease,
             letter-spacing .2s ease;
}
.stButton>button:hover{transform:translateY(-3px) scale(1.02);
  letter-spacing:.5px}
.stButton>button:active{transform:translateY(0) scale(.97);
  box-shadow:var(--glass-top)}

/* ---- SIGN IN + CREATE ACCOUNT ---- */
.stFormSubmitButton>button{
  position:relative; overflow:hidden;
  transition:transform .2s cubic-bezier(.2,.8,.2,1), box-shadow .2s ease,
             letter-spacing .2s ease;
}
.stFormSubmitButton>button:hover{transform:translateY(-3px) scale(1.015);
  letter-spacing:1.4px}
.stFormSubmitButton>button:active{transform:translateY(0) scale(.98)}

/* ---- Sign In / Register tabs ---- */
.stTabs [data-baseweb="tab"]{
  position:relative; transition:transform .2s cubic-bezier(.2,.8,.2,1),
             color .2s ease, background .25s ease, box-shadow .25s ease;
}
.stTabs [data-baseweb="tab"]:hover{
  transform:translateY(-2px); color:var(--accent);
  background:var(--accent-soft); box-shadow:var(--glass-top);
}
.stTabs [data-baseweb="tab"][aria-selected="true"]{
  background:var(--card); box-shadow:var(--glass-shadow), var(--glass-top);
}
/* the underline slides between tabs instead of jumping */
.stTabs [data-baseweb="tab-highlight"]{
  transition:all .32s cubic-bezier(.2,.8,.2,1) !important;
  background:linear-gradient(90deg,var(--accent),var(--accent-2)) !important;
  border-radius:99px !important;
}
/* the panel underneath fades up on every tab switch */
.stTabs [data-baseweb="tab-panel"]{
  animation:pageIn .34s cubic-bezier(.22,.9,.28,1) both;
}

/* ---- modals: entrance animation + the X close button ----
   Streamlit has renamed the dialog close button across versions, so
   every known alias is listed rather than guessing at one.

   BUG FIXED IN v3.6.1 — read before touching this selector.
   A bare div[role="dialog"] does NOT only match st.dialog. BaseWeb
   gives every floating layer role="dialog", including the chart-type
   POPOVER body, and it positions that layer with an INLINE transform.
   CSS animations beat inline styles, so animating the popover to
   transform:none wiped out its coordinates and dropped the Bars /
   Pie chart menu into the top-left corner of the page.
   Rule: scope dialog animations to the stDialog wrapper, and never
   animate transform on anything BaseWeb positions itself. */
[data-testid="stDialog"] div[role="dialog"],
[data-testid="stModal"] div[role="dialog"]{
  animation:modalIn .34s cubic-bezier(.22,.9,.28,1) both;
}
/* hard guard: a popover must never inherit an entrance animation */
[data-baseweb="popover"],
[data-baseweb="popover"] div[role="dialog"],
[data-testid="stPopoverBody"]{animation:none !important}
div[role="dialog"] button[kind="header"],
div[role="dialog"] button[kind="headerNoPadding"],
div[role="dialog"] button[aria-label="Close"],
[data-testid="stDialog"] [data-testid^="stBaseButton-header"]{
  border-radius:10px !important;
  transition:transform .28s cubic-bezier(.2,.8,.2,1), color .2s ease,
             background .2s ease !important;
}
div[role="dialog"] button[kind="header"]:hover,
div[role="dialog"] button[kind="headerNoPadding"]:hover,
div[role="dialog"] button[aria-label="Close"]:hover,
[data-testid="stDialog"] [data-testid^="stBaseButton-header"]:hover{
  transform:rotate(90deg) scale(1.18) !important;
  color:var(--danger) !important;
  background:rgba(224,49,49,.12) !important;
}

/* ---- small polish: reputation tiles and table rows ---- */
.numcard .nb{transition:transform .22s cubic-bezier(.2,.8,.2,1),
                        box-shadow .22s ease}
.numcard .nb:hover{transform:translateY(-4px);
  box-shadow:var(--shadow-hov), var(--glass-top)}
.asea-table tr{transition:background .18s ease}
.asea-table tbody tr:hover{background:var(--accent-soft)}

/* ==================================================================
   v4.9 — NO RED ACCENT ANYWHERE + FROSTED-GLASS INPUTS
   Appended LAST on purpose: these rules must out-cascade both
   Streamlit's defaults and every earlier block in this file.

   WHY THE RED APPEARED AT ALL: Streamlit's built-in theme colour is
   primaryColor #FF4B4B. It paints the focused input ring, the caret,
   the selected Sign In / Register tab label and its underline. The
   earlier rules styled the <input> element but NOT the BaseWeb
   wrapper around it, and used no !important on the tab colours, so
   the red kept winning.

   OPTIONAL belt-and-braces (kills it at the source as well) —
   create .streamlit/config.toml next to secrets.toml:
       [theme]
       primaryColor = "#5c7cfa"
   ================================================================== */

/* ---- tabs: accent label + accent underline, never red ---- */
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] div{color:var(--muted) !important}
.stTabs [data-baseweb="tab"]:hover p{color:var(--accent) !important}
.stTabs [data-baseweb="tab"][aria-selected="true"] p,
.stTabs [data-baseweb="tab"][aria-selected="true"] div{
  color:var(--accent) !important; font-weight:700 !important}
.stTabs [data-baseweb="tab-highlight"]{
  background:linear-gradient(90deg,var(--accent),var(--accent-2)) !important;
  border-radius:99px !important; height:3px !important}
.stTabs [data-baseweb="tab-border"]{background:var(--line) !important}

/* ---- BaseWeb wrapper: it owns the visible plate; make it invisible
        so the frosted <input> underneath is what you actually see ---- */
[data-baseweb="input"], [data-baseweb="base-input"],
[data-baseweb="textarea"], .stTextInput div[data-baseweb],
.stTextArea div[data-baseweb]{
  background:transparent !important; border:none !important;
  box-shadow:none !important}

/* ---- every input box: frosted glass, same language as the cards ---- */
.stTextInput input, .stTextArea textarea, .stNumberInput input{
  border:1px solid var(--glass-edge) !important; border-radius:12px !important;
  background:linear-gradient(135deg,var(--glass-sheen),
             rgba(255,255,255,0) 70%), var(--card-2) !important;
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  box-shadow:var(--glass-top), 0 4px 14px rgba(20,28,50,.10) !important;
  color:var(--ink) !important; caret-color:var(--accent) !important;
  transition:border-color .2s ease, box-shadow .2s ease,
             backdrop-filter .25s ease !important}
.stTextInput input:hover, .stTextArea textarea:hover{
  border-color:rgba(120,150,230,.55) !important}
.stTextInput input:focus, .stTextArea textarea:focus,
.stTextInput input:focus-visible, .stTextArea textarea:focus-visible{
  border-color:var(--accent) !important; outline:none !important;
  box-shadow:0 0 0 4px var(--accent-soft), var(--glass-top) !important;
  -webkit-backdrop-filter:blur(15px) saturate(210%) !important;
  backdrop-filter:blur(15px) saturate(210%) !important}
.stTextInput input::placeholder, .stTextArea textarea::placeholder{
  color:var(--muted) !important}
/* Chrome/Safari autofill paints a solid plate over the glass — stop it */
.stTextInput input:-webkit-autofill,
.stTextInput input:-webkit-autofill:focus{
  -webkit-text-fill-color:var(--ink) !important;
  -webkit-box-shadow:0 0 0 1000px var(--card-2) inset, var(--glass-top) !important;
  transition:background-color 9999s ease-out 0s !important}

/* ---- Sign In / Register sheet + every form = one frosted pane ---- */
[data-testid="stForm"]{
  border:1px solid var(--glass-edge) !important; background:var(--card) !important;
  -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  backdrop-filter:blur(var(--glass-blur)) saturate(var(--glass-sat)) !important;
  box-shadow:var(--glass-shadow), var(--glass-top) !important;
  border-radius:var(--radius) !important}

/* ---- RA 10173 consent checkbox: accent fill, not red ---- */
[data-baseweb="checkbox"] div[data-checked="true"],
[data-testid="stCheckbox"] span[data-baseweb="checkbox"] div:first-child{
  background:linear-gradient(120deg,var(--accent),var(--accent-2)) !important;
  border-color:var(--accent) !important}

/* ---- labels stay legible on glass; spinner uses the accent ---- */
.stTextInput label, .stTextArea label,
[data-testid="stWidgetLabel"] p{color:var(--ink) !important; font-weight:600 !important}
[data-testid="stSpinner"] svg circle{stroke:var(--accent) !important}
"""

# ======================================================================
#  THE ANIMATED BACKGROUND LAYER
#  Built ONCE at import time and pushed as a single, byte-identical
#  element on every rerun. Because the string never changes, Streamlit
#  reuses the existing DOM node instead of remounting it — so the CSS
#  animations keep running straight through page and tab switches.
# ======================================================================
SCAM_TOKENS = [
    "CONGRATULATIONS! You won ₱25,000",
    "Click here → bit.ly/xY7z2q",
    "OTP: 483920 — do not share",
    "GCASH verification required",
    "LOAN APPROVED · 0% interest",
    "Pasaload po, emergency!",
    "Parcel on hold · pay ₱180 fee",
]

_BUBBLES = "".join(
    f'<div class="bub b{i}"><i></i><i></i><i></i></div>' for i in range(1, 7))
_TOKENS = "".join(
    f'<div class="tok t{i+1}">{html.escape(t)}</div>'
    for i, t in enumerate(SCAM_TOKENS))
_VERDICTS = ('<div class="vd spam v1">SPAM</div>'
             '<div class="vd ham v2">HAM</div>'
             '<div class="vd spam v3">SPAM</div>'
             '<div class="vd ham v4">HAM</div>')

BG_HTML = ('<div class="asea-bg">'
           '<div class="aurora a1"></div><div class="aurora a2"></div>'
           '<div class="aurora a3"></div><div class="grid"></div>'
           '<div class="shield">🛡️</div>'
           + _BUBBLES + _TOKENS + _VERDICTS +
           '<div class="radar"></div><div class="ping"></div>'
           '<div class="ping p2"></div><div class="scan"></div>'
           '</div>')

# Stylesheet + backdrop shipped as ONE element, identical on every run.
st.markdown("<style>" + CSS + "</style>" + BG_HTML, unsafe_allow_html=True)

# ================= Shared UI =================
def hero(title, subtitle=""):
    st.markdown(
        '<div class="hero">'
        '<div class="tagline">Anti-Spam Engineered Attacks</div>'
        '<h1 class="brand">A.S.E.A.</h1>'
        f'<div class="ptitle">{html.escape(title)}</div>'
        + (f'<p class="psub">{html.escape(subtitle)}</p>' if subtitle else "")
        + '</div>', unsafe_allow_html=True)

def badge(text, kind="neutral"):
    return f'<span class="badge {kind}">{html.escape(str(text))}</span>'

def verdict_kind(v):
    return "danger" if "SPAM" in str(v).upper() else "safe"

def risk_kind(r):
    r = str(r).upper()
    if "HIGH" in r:   return "danger"
    if "MEDIUM" in r: return "warn"
    if "LOW" in r:    return "caution"
    return "safe"

def kpi_card(col, num, label, icon="", delay=0.0):
    col.markdown(
        f'<div class="card kpi" style="animation-delay:{delay}s">'
        f'<div class="ico">{icon}</div>'
        f'<div class="num">{num}</div>'
        f'<div class="lbl">{html.escape(label)}</div></div>',
        unsafe_allow_html=True)

def meter(pct, kind="neutral"):
    colors = {"danger": "linear-gradient(90deg,#ff8787,#e03131)",
              "safe":   "linear-gradient(90deg,#69db7c,#2f9e44)",
              "warn":   "linear-gradient(90deg,#ffd43b,#f08c00)",
              "caution":"linear-gradient(90deg,#ffe066,#f59f00)",
              "neutral":"linear-gradient(90deg,#5c7cfa,#9775fa)"}
    pct = max(0, min(100, float(pct)))
    return (f'<div class="meter"><span style="width:{pct:.1f}%;'
            f'background:{colors.get(kind, colors["neutral"])}"></span></div>')

def _reasons_from(payload):
    """Pull the occlusion output off an API response.

    Depending on how api.py serialises top_tokens(), the explanation can
    arrive under any of these key names. Accepting all of them means the
    chips render regardless of which one your backend actually uses."""
    if not isinstance(payload, dict):
        return []
    for key in ("reasons", "reason", "top_tokens", "tokens",
                "explanations", "explanation", "keywords"):
        v = payload.get(key)
        if isinstance(v, (list, tuple)) and len(v) > 0:
            return list(v)
        if isinstance(v, str) and v.strip():
            return [v]
    return []

def _chip_label(x):
    """A reason may be a plain string, a (token, score) pair, or a dict.
    Render all three legibly instead of dumping a Python repr."""
    if isinstance(x, dict):
        word = x.get("token") or x.get("word") or x.get("text") or ""
        score = x.get("score", x.get("weight"))
        if word and score is not None:
            try:
                return "%s  ·  %+.2f" % (word, float(score))
            except (TypeError, ValueError):
                return "%s  ·  %s" % (word, score)
        return str(word or x)
    if isinstance(x, (list, tuple)) and len(x) >= 2:
        try:
            return "%s  ·  %+.2f" % (x[0], float(x[1]))
        except (TypeError, ValueError):
            return "%s  ·  %s" % (x[0], x[1])
    return str(x)

def token_chips(reasons, kind="danger"):
    """Renders the model's occlusion reasons as chips."""
    reasons = [x for x in (reasons or []) if str(x).strip()]
    if not reasons:
        return ('<p style="color:var(--muted);font-size:13px;margin:2px 0">'
                'No token-level explanation was returned for this check.</p>')
    cls = "tokchip" if kind == "danger" else "tokchip safe"
    chips = "".join(
        f'<span class="{cls}" style="animation-delay:{min(i * .04, .4):.2f}s">'
        f'{html.escape(_chip_label(x))}</span>' for i, x in enumerate(reasons))
    return f'<div class="tokchips">{chips}</div>'

def msgbox_html(text):
    """Render a message body inside a .msgbox.

    CRITICAL: the result must be a SINGLE line. A real newline inside a
    raw <div> makes Streamlit's markdown parser close the HTML block
    early and silently drop everything after it — which is exactly why
    multi-line SMS bodies were showing up as an empty box. Escaping
    first, then converting newlines to <br>, fixes it."""
    s = str(text if text is not None else "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = html.escape(s).replace("\n", "<br>")
    if not s.strip():
        return ('<div class="msgbox"><span style="color:var(--muted)">'
                'This record was saved without the full message body.'
                '</span></div>')
    return '<div class="msgbox">' + s + '</div>'

def table_html(headers, rows):
    head = "".join(f"<th>{h}</th>" for h in headers)
    if rows:
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                       for r in rows)
    else:
        body = (f'<tr><td colspan="{len(headers)}" '
                'style="text-align:center;color:#6b7280">— nothing yet —</td></tr>')
    return (f'<table class="asea-table"><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table>')

def footer():
    st.markdown("""
<div class="site-footer">
  <div class="frow">
    <div>
      <div>
        <svg viewBox="0 0 24 24"><path d="M13 22v-8h3l1-4h-4V7.5C13 6.5 13.5 6 14.5 6H17V2h-3.5C11 2 9 4 9 6.5V10H6v4h3v8h4z"/></svg>
        <svg viewBox="0 0 24 24"><path d="M7 2h10c2.8 0 5 2.2 5 5v10c0 2.8-2.2 5-5 5H7c-2.8 0-5-2.2-5-5V7c0-2.8 2.2-5 5-5zm5 5a5 5 0 100 10 5 5 0 000-10zm0 2a3 3 0 110 6 3 3 0 010-6zm5.5-3.2a1.2 1.2 0 100 2.4 1.2 1.2 0 000-2.4z"/></svg>
        <svg viewBox="0 0 24 24"><path d="M14 2v12.5a2.5 2.5 0 11-2.5-2.5h.5V8.5h-.5A6.5 6.5 0 1018 15V8.7a8 8 0 004 1.1V5.8c-2.2 0-4-1.7-4-3.8h-4z"/></svg>
      </div>
      <div class="hashtag">#ToServeandProtect</div>
    </div>
    <div class="contact">
      <a href="mailto:acg.rac03@gmail.com">acg.rac03@gmail.com</a> / <a href="mailto:racu3@acg.pnp.gov.ph">racu3@acg.pnp.gov.ph</a><br>
      Pampanga: Camp Olivas, City of San Fernando<br>
      +63 998 598 8102
    </div>
  </div>
  <div class="copy">A.S.E.A. © 2026 · All Rights Reserved</div>
</div>
""", unsafe_allow_html=True)

# ================= Storage =================
HISTORY_FILE = "history_store.json"
PROFILE_FILE = "profile_store.json"

def _load_all_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_history(email, history):
    if not email:
        return
    allh = _load_all_history()
    allh[email] = history
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(allh, f, ensure_ascii=False, indent=2)

def _get_since(email):
    if not email:
        return date.today().isoformat()
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            profs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        profs = {}
    if not profs.get(email, {}).get("since"):
        profs.setdefault(email, {})["since"] = date.today().isoformat()
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(profs, f, ensure_ascii=False, indent=2)
    return profs[email]["since"]

def log_check(kind, snippet, full_input, result, detail=None, sender=""):
    """Saves the FULL input, the sender, and the raw API response."""
    ss["history"].insert(0, {"when": time.strftime("%Y-%m-%d %H:%M"),
                             "type": kind, "input": snippet,
                             "full_input": full_input, "sender": sender,
                             "result": result, "detail": detail or {}})
    ss["history"] = ss["history"][:50]
    _save_history(ss.get("user"), ss["history"])

def number_reputation(number):
    """Reputation for a sender, via the EXISTING /verify-number endpoint.
    No backend change; cached per number so reopening a modal is free."""
    number = (number or "").strip()
    if not number:
        return None
    if number in ss["numcache"]:
        return ss["numcache"][number]
    try:
        # ---------- UNCHANGED API CALL (Step 7c contract) ----------
        r = requests.post(f"{API_BASE}/verify-number",
                          json={"number": number}, timeout=30).json()
        # -----------------------------------------------------------
    except Exception:
        r = None
    ss["numcache"][number] = r
    return r

# ================= Result pop-ups =================
@st.dialog("Analysis result", width="large")
def text_result_dialog(r):
    v = r.get("verdict", "—")
    conf = float(r.get("confidence", 0) or 0) * 100
    k = verdict_kind(v)
    st.markdown(f'<div style="text-align:center">{badge(v, k)}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<p style="text-align:center;color:var(--muted);margin-top:10px">'
                f'{html.escape(str(r.get("sub", "")))}</p>', unsafe_allow_html=True)
    st.markdown(f'<div class="sec-title" style="margin-top:14px">Confidence '
                f'· {conf:.1f}%</div>{meter(conf, k)}', unsafe_allow_html=True)
    # v5.5 — the section only exists for a SPAM verdict. subtype is None on
    # HAM (Step 6 contract), so this also hides the empty-state caption.
    if r.get("subtype"):
        st.markdown('<div class="sec-title">Words that made this a red flag</div>'
                    + token_chips(_reasons_from(r), k), unsafe_allow_html=True)
    st.markdown(table_html(["Field", "Value"], [
        ["Model", html.escape(str(r.get("model", "—")))],
        ["Spam type", html.escape(str(r.get("subtype") or "—"))],
        ["Confidence", f"{conf:.1f}%"],
        ["Latency", f"{r.get('latency_ms', '—')} ms"],
    ]), unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;font-style:italic;margin-top:18px;'
                'color:var(--muted)">Thank you for using A.S.E.A.</p>',
                unsafe_allow_html=True)
    if st.button("Close", key="close_vt", type="primary", use_container_width=True):
        st.rerun()

@st.dialog("Number reputation", width="large")
def number_result_dialog(r):
    risk = r.get("risk", "—")
    k = risk_kind(risk)
    reports = int(r.get("reports", 0) or 0)
    st.markdown(f'<div style="text-align:center">{badge(risk, k)}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="sec-title" style="margin-top:16px">Report volume '
                f'· {reports}</div>{meter(min(reports, 30) / 30 * 100, k)}',
                unsafe_allow_html=True)
    st.markdown(table_html(["Field", "Value"], [
        ["Hashed sender (SHA-256)", html.escape(str(r.get("hashed", "—")))],
        ["Total reports", reports],
        ["Top scam type", html.escape(str(r.get("top_type") or "—"))],
    ]), unsafe_allow_html=True)
    st.caption("🔒 The raw number is never stored — only its SHA-256 digest. RA 10173 compliant.")
    if st.button("Close", key="close_vn", type="primary", use_container_width=True):
        st.rerun()

@st.dialog("Check details", width="large")
def history_detail_dialog(h):
    d = h.get("detail") or {}
    is_text = h.get("type") == "Text"
    res = h.get("result", "—")
    k = verdict_kind(res) if is_text else risk_kind(res)
    sender = (h.get("sender") or "").strip()
    category = (d.get("subtype") if is_text else d.get("top_type")) or "Uncategorised"

    # ---- headline ----
    st.markdown(
        f'<div style="text-align:center">{badge(res, k)}'
        f'&nbsp;&nbsp;{badge(category, "neutral")}</div>', unsafe_allow_html=True)
    st.markdown(f'<p style="text-align:center;color:var(--muted);font-size:12px;'
                f'margin-top:8px">Checked {html.escape(h.get("when", ""))}</p>',
                unsafe_allow_html=True)

    # ---- 1. tokens that drove the category ----
    if is_text and d.get("subtype"):        # v5.5 — SPAM records only
        st.markdown(f'<div class="sec-title" style="margin-top:16px">'
                    f'Words that made this a red flag · {html.escape(str(category))}'
                    f'</div>' + token_chips(_reasons_from(d), k),
                    unsafe_allow_html=True)

    # ---- 2. the full message ----
    # NOTE: msgbox_html() collapses newlines to <br> first. Passing raw
    # multi-line text straight to st.markdown drops most of the message.
    st.markdown('<div class="sec-title" style="margin-top:16px">'
                'Full text message</div>', unsafe_allow_html=True)
    st.markdown(msgbox_html(h.get("full_input") or h.get("input") or ""),
                unsafe_allow_html=True)

    # ---- 3. sender + that number's scam record ----
    st.markdown('<div class="sec-title" style="margin-top:18px">'
                'Sender reputation</div>', unsafe_allow_html=True)
    if not sender:
        st.info("No phone number was entered with this check, so there is "
                "nothing to look up. Fill in the Contact Number field on "
                "Verify Text to capture it next time.")
    else:
        rep = number_reputation(sender)
        if rep is None:
            st.warning(f"Saved sender: **{sender}** — but the reputation table "
                       "could not be reached. Is `uvicorn api:app` running?")
        else:
            reports = int(rep.get("reports", 0) or 0)
            top = rep.get("top_type") or "—"
            rk = risk_kind(rep.get("risk", ""))
            st.markdown(
                '<div class="numcard">'
                f'<div class="nb"><div class="t">Phone number</div>'
                f'<div class="v">{html.escape(sender)}</div></div>'
                f'<div class="nb"><div class="t">Scam reports on file</div>'
                f'<div class="v">{reports}</div></div>'
                f'<div class="nb"><div class="t">Most involved in</div>'
                f'<div class="v small">{html.escape(str(top))}</div></div>'
                '</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="sec-title" style="margin-top:14px">'
                        f'Risk level · {html.escape(str(rep.get("risk", "—")))}'
                        f'</div>{meter(min(reports, 30) / 30 * 100, rk)}',
                        unsafe_allow_html=True)
            st.caption("🔒 Looked up by SHA-256 digest — the raw number is "
                       "never stored server-side. RA 10173 compliant.")

    # ---- 4. model diagnostics ----
    if not d:
        st.info("This check was saved before detailed logging was added, so only "
                "the summary is available. New checks store everything.")
    elif is_text:
        conf = float(d.get("confidence", 0) or 0) * 100
        st.markdown(f'<div class="sec-title" style="margin-top:18px">'
                    f'Model confidence · {conf:.1f}%</div>{meter(conf, k)}',
                    unsafe_allow_html=True)
        st.markdown(table_html(["Field", "Value"], [
            ["Verdict", html.escape(str(d.get("verdict", "—")))],
            ["Category", html.escape(str(d.get("subtype") or "—"))],
            ["Model used", html.escape(str(d.get("model", "—")))],
            ["Confidence", f"{conf:.1f}%"],
            ["Inference latency", f"{d.get('latency_ms', '—')} ms"],
        ]), unsafe_allow_html=True)
    else:
        st.markdown('<div class="sec-title" style="margin-top:18px">'
                    'Lookup record</div>', unsafe_allow_html=True)
        st.markdown(table_html(["Field", "Value"], [
            ["Risk band", html.escape(str(d.get("risk", "—")))],
            ["Total reports", int(d.get("reports", 0) or 0)],
            ["Top scam type", html.escape(str(d.get("top_type") or "—"))],
            ["Hashed sender", html.escape(str(d.get("hashed", "—")))],
        ]), unsafe_allow_html=True)

    if st.button("Close", key="close_hist", type="primary", use_container_width=True):
        st.rerun()

# ================= Auth screen =================
def auth_screen():
    # Turns the backdrop up to "intense". Changing a CSS variable does NOT
    # restart any animation, so the motion stays perfectly continuous.
    st.markdown("<style>.asea-bg{--boost:1}</style>", unsafe_allow_html=True)
    hero("Sign In or Register",
         "Real-time SMS scam detection powered by a fine-tuned BERT model.")
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        tab_in, tab_up = st.tabs(["Sign In", "Register"])
        with tab_in:
            with st.form("signin_form"):
                email = st.text_input("Email", key="in_email",
                                      placeholder="you@example.com")
                pw = st.text_input("Password", type="password", key="in_pw",
                                   placeholder="••••••••")
                signin = st.form_submit_button("SIGN IN", use_container_width=True)
            if signin:
                # ---------- UNCHANGED Firebase logic (Step 7c) ----------
                try:
                    account = auth.sign_in_with_email_and_password(email, pw)
                    display = ss["names"].get(email, "")
                    try:
                        info = auth.get_account_info(account["idToken"])
                        display = info["users"][0].get("displayName") or display
                    except Exception:
                        pass
                    ss["user"] = email
                    ss["name"] = display or email.split("@")[0]
                    ss["names"][email] = ss["name"]
                    ss["history"] = _load_all_history().get(email, [])
                    ss["since"] = _get_since(email)
                    ss["page"] = "Dashboard"
                    st.rerun()
                except Exception:
                    st.error("Invalid email or password.")
                # --------------------------------------------------------
            st.caption("Use the email and password you registered with.")
        with tab_up:
            with st.form("register_form"):
                name = st.text_input("Full name", key="up_name",
                                     placeholder="Juan Dela Cruz")
                email = st.text_input("Email", key="up_email",
                                      placeholder="you@example.com")
                pw = st.text_input("Password (min 6 chars)", type="password",
                                   key="up_pw", placeholder="••••••••")
                pw2 = st.text_input("Confirm password", type="password",
                                    key="up_pw2", placeholder="••••••••")
                tos = st.checkbox("I agree to the RA 10173 anonymized data use.",
                                  key="up_tos")
                register = st.form_submit_button("CREATE ACCOUNT",
                                                 use_container_width=True)
            if register:
                # ---------- UNCHANGED Firebase logic (Step 7c) ----------
                if not name or not email or not pw:
                    st.error("Please fill in your name, email, and password.")
                elif pw != pw2:
                    st.error("Passwords do not match.")
                elif not tos:
                    st.error("Please accept the data use agreement.")
                else:
                    try:
                        user = auth.create_user_with_email_and_password(email, pw)
                        try:
                            auth.update_profile(user["idToken"], display_name=name)
                        except Exception:
                            pass
                        try:
                            auth.send_email_verification(user["idToken"])
                        except Exception:
                            pass
                        ss["names"][email] = name
                        st.success("Account created — switch to the Sign In tab to log in.")
                        st.balloons()
                    except Exception:
                        st.error("Could not register (email may be in use, "
                                 "or password too weak).")
                # --------------------------------------------------------
    footer()

# ================= Navigation =================
# Account is NOT here — it lives in the user chip's dropdown, top-right.
NAV = ["Dashboard", "Verify Number", "Verify Text", "History"]

def top_nav():
    left, _spacer, right = st.columns([1.5, 1.4, 1])

    # ---- A.S.E.A. logo + hover dropdown ----
    with left:
        menu = st.container()
        with menu:
            # MUST be the first element in this container (CSS relies on it)
            st.markdown(
                '<div class="asea-menu-marker">'
                '<span class="logo">A.S.E.A.</span>'
                '<span class="caret">▾</span>'
                f'<span class="cur">{html.escape(ss["page"])}</span>'
                '</div>', unsafe_allow_html=True)
            for label in NAV:                       # no icons, plain labels
                if st.button(label, key=f"nav_{label}",
                             use_container_width=True,
                             type="primary" if ss["page"] == label else "secondary"):
                    ss["page"] = label
                    st.rerun()

    # ---- user glass chip + hover dropdown (Account, then LOG OUT) ----
    with right:
        usermenu = st.container()
        with usermenu:
            # MUST be the first element in this container (CSS relies on it)
            st.markdown(
                '<div style="text-align:right">'
                '<div class="asea-user-marker">'
                '<span class="who">'
                f'<span class="nm">{html.escape(ss["name"])}</span><br>'
                f'<span class="em">{html.escape(ss["user"])}</span>'
                '</span><span class="caret">▾</span>'
                '</div></div>', unsafe_allow_html=True)

            # row 1 — Account
            if st.button("Account", key="user_account",
                         use_container_width=True,
                         type="primary" if ss["page"] == "Account"
                         else "secondary"):
                ss["page"] = "Account"
                st.rerun()

            # row 2 — LOG OUT, inside its OWN container with its OWN marker
            # so every red-gradient and hover rule keeps applying exactly
            # as before. Do not flatten this nesting.
            logout = st.container()
            with logout:
                st.markdown('<div class="asea-logout-marker"></div>',
                            unsafe_allow_html=True)
                if st.button("LOG OUT", key="btn_logout",
                             use_container_width=True):
                    ss["user"] = None; ss["name"] = ""; ss["since"] = ""
                    st.rerun()
    return ss["page"]

# ================= History rows (shared) =================
def render_history_rows(items, keyprefix):
    if not items:
        st.markdown('<div class="card flat empty"><span class="big">🕊️</span>'
                    'No checks yet — run one from Verify Text or Verify Number.'
                    '</div>', unsafe_allow_html=True)
        return
    for i, h in enumerate(items):
        c1, c2 = st.columns([9, 1.6])
        k = verdict_kind(h["result"]) if h.get("type") == "Text" \
            else risk_kind(h["result"])
        icon = "💬" if h.get("type") == "Text" else "☎️"
        c1.markdown(
            f'<div class="card" style="padding:13px 18px;margin-bottom:9px;'
            f'animation-delay:{min(i * 0.05, 0.5)}s">'
            f'<div class="hrow"><span style="font-size:17px">{icon}</span>'
            f'<span class="when">{html.escape(h.get("when", ""))}</span>'
            f'<span class="snip">{html.escape(str(h.get("input", "")))}</span>'
            f'{badge(h.get("result", "—"), k)}</div></div>',
            unsafe_allow_html=True)
        c2.markdown('<div style="height:9px"></div>', unsafe_allow_html=True)
        if c2.button("View", key=f"{keyprefix}_{i}", use_container_width=True):
            history_detail_dialog(h)

# ================= Dashboard chart =================
SCAM_TYPES = [("Gambling Scam", 38), ("Delivery Scam", 22), ("Prize Scam", 14),
              ("Investment Scam", 12), ("Commercial Spam", 8), ("Other", 6)]
CHART_VIEWS = ["Bars", "Pie chart"]
CHART_COLORS = ["#3b5bdb", "#7048e8", "#22b8cf",
                "#4c6ef5", "#9775fa", "#748ffc"]

def render_scam_chart():
    """Bars = the styled HTML meters (default).
    Pie chart = an Altair donut. Altair ships with Streamlit as a hard
    dependency, so there is nothing extra to install."""
    view = ss.get("chart_view", "Bars")

    if view == "Bars":
        # The 26px top margin is INLINE on our own wrapper div, not a CSS
        # rule. Panel-scoped selectors for this gap kept missing because
        # Streamlit nests the columns row; inline styling always applies.
        st.markdown('<div style="margin-top:26px">' + "".join(
            f'<div class="barlabel"><span>{html.escape(nm)}</span>'
            f'<strong>{pct}%</strong></div>'
            f'<div class="bar"><span style="width:{pct}%;'
            f'animation-delay:{0.15 + j * 0.09:.2f}s"></span></div>'
            for j, (nm, pct) in enumerate(SCAM_TYPES)) + '</div>',
            unsafe_allow_html=True)
        return

    try:
        import pandas as pd
        import altair as alt
    except ImportError:
        st.info("The Pie chart view needs pandas and altair. "
                "Install them with:  pip install pandas altair")
        return

    df = pd.DataFrame(SCAM_TYPES, columns=["Scam type", "Share"])
    scale = alt.Scale(range=CHART_COLORS)

    # Hover tooltips are enabled. The orphaned-tooltip bug that v2.7 was
    # working around is now handled in CSS: #vg-tooltip-element may only
    # paint while a Vega chart is actually under the pointer, so it can
    # never be stranded in the corner. The permanent ring labels stay too,
    # so the numbers still show in a screenshot with no hover.
    base = alt.Chart(df).encode(theta=alt.Theta("Share:Q", stack=True))
    donut = (base.mark_arc(innerRadius=58, outerRadius=112, cornerRadius=4,
                           stroke="#ffffff", strokeWidth=2)
             .encode(color=alt.Color("Scam type:N", scale=scale,
                                     legend=alt.Legend(title=None,
                                                       orient="right")),
                     tooltip=[alt.Tooltip("Scam type:N",
                                          title="Classification"),
                              alt.Tooltip("Share:Q", title="Share (%)",
                                          format=".0f")]))
    labels = base.mark_text(radius=133, size=11, fontWeight="bold",
                            color="#8a93a6").encode(
        text=alt.Text("Share:Q", format=".0f"))
    chart = (donut + labels).properties(height=280)

    # matching spacer so the donut sits at the same offset as the bars
    st.markdown('<div style="height:26px"></div>', unsafe_allow_html=True)
    st.altair_chart(chart.configure_view(strokeWidth=0)
                         .configure(background="transparent"),
                    use_container_width=True)

# ================= Screenshot OCR (v5.0) =================
# The DE's reference implementation ran Tesseract.js in the browser.
# Streamlit cannot execute custom JavaScript (st.markdown sanitises it), so
# the identical job is done server-side with pytesseract — a thin wrapper
# around the SAME Tesseract engine. Same OCR, same regex parsing, one less
# moving part, and the extracted values land directly in session state.
#
# NOTHING HERE TOUCHES THE BACKEND CONTRACT. OCR only fills the two fields
# the user could already have typed by hand; /predict-text still receives
# exactly {"sender": ..., "text": ...}.

# The DE's phone pattern, ported to Python and tightened. Requires a digit
# at both ends so it cannot latch onto a trailing separator, and 9-19
# characters so amounts like "25,000" are never mistaken for a number.
PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,17}\d")

# ---------------------------------------------------------------------
#  v5.2 — INPUT NORMALISATION (the fix for "same message, two verdicts")
#  A transformer sees characters, not meaning: "Atty.Nympha" and
#  "Atty. Nympha", or a blank line before "Thank You.", tokenise
#  differently and can land on different sides of a decision boundary.
#  EVERY route into /predict-text — pasted text, OCR output, an edited OCR
#  result — is funnelled through normalize_text() first, so the same
#  wording always produces the same verdict.
# ---------------------------------------------------------------------
ZW_RE = re.compile(r"[-‍﻿]")          # zero-width junk
# "Atty.Nympha" -> "Atty. Nympha", while leaving "bit.ly" and initialisms
# such as "U.S.A." alone (lower-case follower / single-capital lookbehind).
DOT_GLUE_RE = re.compile(r"(?<![A-Z]\.)(?<=[.!?])(?=[A-Z])")
PUNCT_GLUE_RE = re.compile(r"(?<=[,;:])(?=[A-Za-z])")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:])")

def normalize_text(s):
    """Canonical surface form of a message, sent to the API verbatim."""
    zw = (chr(0x200b), chr(0x200c), chr(0x200d), chr(0xfeff))
    s = "".join(c for c in (s or "") if c not in zw)   # v5.4: chr(), not
    # \u escapes — Notion rewrites them inside code blocks, and the mangled
    # class below was deleting every HYPHEN from the message. Line kept as
    # a comment only: re.sub('[\-\‍\﻿]', "", s or "")   # v5.3: escapes, not literals
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-"))
    s = re.sub(r"\s+", " ", s)            # wraps and blank lines -> one space
    s = DOT_GLUE_RE.sub(" ", s)
    s = PUNCT_GLUE_RE.sub(" ", s)
    s = SPACE_BEFORE_PUNCT_RE.sub(r"\1", s)
    return s.strip()

# Interface furniture that messaging apps stamp onto every screenshot.
# Extends the DE's filter list with the banners seen on PH handsets.
# v5.1: word boundaries are load-bearing. Without them "mon" was deleted out
# of "money" and "sat" out of "satisfied", quietly mutilating the message
# before the model ever saw it.
UI_NOISE_RE = re.compile(
    r"\b(maybe spam|text message|imessage|sms|not spam|report junk|"
    r"this conversation from an unknown sender|filtered as spam|unknown sender|"
    # v5.4 — the trailer iOS/Android stamp under an unknown-sender thread.
    r"the sender is not in your contact list|"
    r"sender is not in your contacts|tap to load preview|"
    r"message blocking is active|"
    r"today|yesterday|delivered|read receipt|"
    r"mon|tue|wed|thu|fri|sat|sun)\b[,.:]?", re.I)

# v5.4 — the date stamp a thread screenshot carries above the bubble:
# "Nov 4 at 8:01 PM", "4 Nov 2025, 20:01". It is metadata, not message
# content, and left in place the model scores it as part of the SMS.
DATE_STAMP_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*"
    r"\d{1,2}(?:\s*,?\s*\d{4})?(?:\s*(?:at|@)?\s*\d{1,2}[:.]\d{2}"
    r"\s*(?:am|pm)?)?", re.I)

# v5.4 — glyph soup OCR invents for status-bar and avatar icons, e.g. the
# "\\<@®" that opened the PHLPOST screenshot. Keep letters, digits, normal
# punctuation, URLs and the peso sign; drop the rest.
JUNK_GLYPH_RE = re.compile(r"[^\w\s.,!?;:'\"()\[\]/@#&+%$₱-]+")

# A line that is nothing but a clock reading — "9:41", "11.27 PM".
TIME_RE = re.compile(r"^\s*\d{1,2}[:.]\d{2}\s*(am|pm)?\s*$", re.I)

# v5.1: whole lines that are handset chrome rather than message content —
# the carrier/status bar ("eeceo Smart 4G 9:05 AM 75% a)") and the thread
# navigation bar ("< Messages   Details").
STATUS_RE = re.compile(
    r"^\s*[<>«»]?\s*(?:"
    r"(?=.*\d{1,2}[:.]\d{2})(?=.*(?:\d{1,3}\s*%|\b(?:lte|4g|5g|3g|wi-?fi)\b)).*"
    r"|(?:\W*\b(?:messages|details|back|contact|info|edit|cancel|done|call|"
    r"facetime|delete)\b\W*)+"
    r")\s*$", re.I)

def ocr_image(image_bytes):
    """Run Tesseract over an uploaded screenshot.
    Returns (text, error_message) and never raises — a missing engine is a
    normal, recoverable state that must be explained, not a crash."""
    try:
        import io
        from PIL import Image, ImageOps
        import pytesseract
    except ImportError:
        return "", ("Screenshot reading needs two extra libraries. Install "
                    "them with:   pip install pillow pytesseract   "
                    "and the engine itself with:   brew install tesseract")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("L")   # upright, greyscale
        if img.width < 1000:              # phone screenshots are small; Tesseract
            img = img.resize((img.width * 2, img.height * 2))   # reads 2x better
        img = ImageOps.autocontrast(img)
        return pytesseract.image_to_string(img), ""
    except Exception as ex:
        if "tesseract" in str(ex).lower():
            return "", ("The Tesseract engine is not installed, or not on PATH. "
                        "On macOS:   brew install tesseract")
        return "", f"Could not read that image: {ex}"

def parse_ocr(raw_text):
    """Split raw OCR output into (phone number, message body)."""
    text = raw_text or ""

    def digits(s):
        return re.sub(r"\D", "", s)

    candidates = [m.group(0) for m in PHONE_RE.finditer(text)]
    number = ""
    if candidates:
        # Prefer something shaped like a real PH mobile — 09XXXXXXXXX or
        # +639XXXXXXXXX — before falling back to "the longest match", which
        # on a noisy screenshot is often an OTP or a reference code.
        ph = [c for c in candidates
              if digits(c).startswith(("09", "639")) or c.strip().startswith("+63")]
        number = max(ph or candidates, key=lambda c: len(digits(c))).strip(" .,-")

    body = PHONE_RE.sub(" ", text) if number else text
    lines = []
    for ln in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if STATUS_RE.match(ln):          # carrier bar / nav bar
            continue
        ln = DATE_STAMP_RE.sub(" ", ln)        # v5.4: "Nov 4 at 8:01 PM"
        ln = UI_NOISE_RE.sub(" ", ln)
        ln = JUNK_GLYPH_RE.sub(" ", ln).strip(" \t|·-–—")
        if not ln or TIME_RE.match(ln):
            continue
        lines.append(ln)

    # v5.1 — UNWRAP. This is the fix for the misclassification. A screenshot
    # breaks one sentence across a dozen narrow lines; the models were
    # fine-tuned on messages written as running text, so those hard breaks
    # fragment the tokenisation and can flip the predicted scam type
    # ("Prize Scam" -> "Commercial Spam"). Rejoin the surviving lines into a
    # single paragraph and squeeze the whitespace, so an OCR'd screenshot and
    # the same message pasted by hand reach the API identically.
    msg = re.sub(r"\s+", " ", " ".join(lines))
    msg = re.sub(r"\s+([,.!?;:])", r"\1", msg)
    return number, normalize_text(msg)

# ================= Screens =================
def dashboard():
    hero("Dashboard", "Snapshot of A.S.E.A. activity today.")
    st.markdown(
        f'<div class="card" style="text-align:center;'
        f'background:linear-gradient(120deg,var(--accent-soft),transparent)">'
        f'<h2 style="margin:0 0 6px;font-size:26px">Welcome back, '
        f'{html.escape(ss["name"])} 👋</h2>'
        f'<p style="color:var(--muted);margin:0">Your model is live and listening.</p>'
        f'</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, len(ss["history"]), "Your checks", "🔍", 0.05)
    kpi_card(c2, "1,284", "Flagged today", "🚩", 0.12)
    kpi_card(c3, "47%", "Phishing share", "🎣", 0.19)
    kpi_card(c4, "95.1%", "Avg confidence", "🎯", 0.26)

    left, rightc = st.columns([1.25, 1])
    with left:
        panel = st.container()
        with panel:
            # MUST be the first element — the glass styling keys off it
            st.markdown('<div class="asea-panel-marker"></div>',
                        unsafe_allow_html=True)
            # NO COLUMN SPLIT HERE — this is the v4.6 fix. The caret used
            # to sit in a 60px st.columns([1, 9]) cell, and an absolutely
            # positioned row can never escape an ancestor that clips it,
            # so the 176px options were sliced off at the column edge
            # ("Bar", "Pie c"). The menu now lives in a FULL-WIDTH
            # container, and the caret is drawn INSIDE the heading's own
            # flex row, which is how it still appears to the LEFT of the
            # title. Do not reintroduce a narrow column here.
            #
            # Mechanism is the logo menu's, unchanged: a marker div this
            # file controls, followed by the option buttons, which the CSS
            # lifts out of flow and drops beneath the marker on hover.
            # It cannot be st.popover — a popover only opens on click,
            # portals its panel to <body> where it cannot be positioned
            # under the caret, and cannot be closed from Python.
            cmenu = st.container()
            with cmenu:
                st.markdown('<div class="asea-chartmenu-row">'
                            '<div class="asea-chartmenu-marker">'
                            '<span class="caret">▾</span></div>'
                            '<div class="sec-title">'
                            'Top scam types this week</div>'
                            '</div>',
                            unsafe_allow_html=True)
                for opt in CHART_VIEWS:
                    if st.button(opt, key=f"cv_{opt}",
                                 use_container_width=True,
                                 type="primary" if ss["chart_view"] == opt
                                 else "secondary"):
                        ss["chart_view"] = opt
                        st.rerun()
            render_scam_chart()
    with rightc:
        st.markdown('<div class="card flat"><div class="sec-title">Quick actions</div>'
                    '<p style="color:var(--muted);margin:0;font-size:13px">'
                    'Jump straight into a check.</p></div>', unsafe_allow_html=True)
        if st.button("Verify a text", key="qa_text",
                     use_container_width=True, type="primary"):
            ss["page"] = "Verify Text"; st.rerun()
        if st.button("Verify a number", key="qa_num", use_container_width=True):
            ss["page"] = "Verify Number"; st.rerun()
        if st.button("Open full history", key="qa_hist", use_container_width=True):
            ss["page"] = "History"; st.rerun()

    st.markdown('<div class="sec-title" style="margin-top:8px">'
                'Your recent checks</div>', unsafe_allow_html=True)
    render_history_rows(ss["history"][:5], "dashrow")

def verify_number_screen():
    hero("Cellphone Number Verification",
         "Check a sender against the hashed reputation table.")
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        num = st.text_input("Contact Number", key="vn_input",
                            placeholder="09XX XXX XXXX")
        b1, b2 = st.columns([2, 1])
        go = b1.button("DETECT", key="vn_detect",
                       use_container_width=True, type="primary")
        if b2.button("Clear", key="vn_clear", use_container_width=True):
            st.rerun()
        if go:
            if not num.strip():
                st.error("Please enter a phone number.")
            else:
                # ---------- UNCHANGED API CALL (Step 7c) ----------
                try:
                    with st.spinner("Checking reputation table…"):
                        r = requests.post(f"{API_BASE}/verify-number",
                                          json={"number": num}, timeout=60).json()
                    summary = r.get("risk", "") + (
                        (" · " + r["top_type"]) if r.get("top_type") else "")
                    ss["numcache"][num.strip()] = r
                    log_check("Number", num, num, summary, r, num)
                    st.toast("Lookup complete", icon="✅")
                    number_result_dialog(r)
                except Exception:
                    st.error("Could not reach the API. "
                             "Is `uvicorn api:app` running on port 8000?")
                # --------------------------------------------------
        st.caption("🔒 Numbers are SHA-256 hashed before lookup. RA 10173 compliant.")

def verify_text_screen():
    hero("Spam / Phishing Detection",
         "Paste an SMS — or upload a screenshot and let OCR read it for you.")
    _, mid, _ = st.columns([1, 2.4, 1])
    with mid:
        # ---- v5.0: screenshot -> OCR -> the same two fields ----
        # Deliberately NOT a separate tab or a mode switch: OCR does not
        # replace the form, it FILLS it. Both fields stay visible and fully
        # editable underneath, so the paste workflow is completely untouched
        # and every extraction is reviewable before DETECT is pressed —
        # which matters, because OCR on a phone screenshot is never perfect.
        #
        # ORDER IS LOAD-BEARING: the uploader must render BEFORE the two
        # inputs. v5.1 no longer writes to a widget key at all — it writes to
        # plain mirror values and bumps vt_nonce, which rebuilds the two
        # inputs as brand-new widgets. Assigning ss["vt_body"] directly was
        # what made the SECOND screenshot look like it did nothing: Streamlit
        # kept the first extraction's widget state and silently ignored it.
        with st.expander("📷  Upload a screenshot of the text message instead"):
            shot = st.file_uploader(
                "Screenshot",
                type=["png", "jpg", "jpeg", "webp", "bmp", "tiff"],
                key=f"vt_shot_{ss['vt_nonce']}",
                help="The sender's number and the message body are extracted "
                     "automatically. Both remain editable below.")
            if shot is None:
                # v5.1: the uploader was emptied. Forget the signature so that
                # re-uploading the SAME file is read again instead of being
                # skipped as a duplicate.
                ss["vt_shot_sig"] = ""
            else:
                raw = shot.getvalue()
                sig = hashlib.sha256(raw).hexdigest()
                # OCR only a NEW image. Streamlit reruns on every interaction,
                # and re-reading the same screenshot would overwrite any
                # correction the user just typed into the fields.
                if ss.get("vt_shot_sig") != sig:
                    with st.spinner("Reading the screenshot…"):
                        text, err = ocr_image(raw)
                    ss["vt_shot_sig"] = sig
                    ss["vt_ocr_err"] = err
                    ss["vt_ocr_raw"] = "" if err else text
                    if not err:
                        num, msg = parse_ocr(text)
                        ss["vt_sender_val"] = num
                        ss["vt_body_val"] = msg
                        ss["vt_nonce"] += 1      # rebuild both inputs
                    st.rerun()
            if ss.get("vt_ocr_err"):
                st.error(ss["vt_ocr_err"])
            elif ss.get("vt_ocr_raw"):
                st.success("Text extracted — check both fields below and fix "
                           "anything OCR misread before running DETECT.")
                st.caption("Raw OCR output")
                st.code(ss["vt_ocr_raw"] or "(nothing legible)")

        sender = st.text_input("Contact Number (optional)",
                               value=ss["vt_sender_val"],
                               key=f"vt_sender_{ss['vt_nonce']}",
                               placeholder="09XX XXX XXXX")
        body = st.text_area("Message", value=ss["vt_body_val"],
                            key=f"vt_body_{ss['vt_nonce']}", height=190,
                            placeholder="Paste the suspicious SMS here…")
        # Keep the mirrors in step with whatever is on screen, so a manual
        # correction survives the next rerun.
        ss["vt_sender_val"], ss["vt_body_val"] = sender, body
        b1, b2 = st.columns([2, 1])
        go = b1.button("DETECT", key="vt_detect",
                       use_container_width=True, type="primary")
        if b2.button("Clear", key="vt_clear", use_container_width=True):
            # v5.1: Clear now really clears — fields, screenshot and OCR panel.
            ss["vt_sender_val"] = ss["vt_body_val"] = ""
            ss["vt_shot_sig"] = ss["vt_ocr_raw"] = ss["vt_ocr_err"] = ""
            ss["vt_nonce"] += 1
            st.rerun()
        if go:
            if not body.strip():
                st.error("Please paste a message.")
            else:
                # ---------- UNCHANGED API CALL (Step 7c) ----------
                try:
                    clean = normalize_text(body)      # v5.2
                    with st.spinner("Analyzing message…"):
                        r = requests.post(f"{API_BASE}/predict-text",
                                          json={"sender": sender, "text": clean},
                                          timeout=60).json()
                    snippet = clean[:60] + ("…" if len(clean) > 60 else "")
                    summary = r.get("verdict", "") + (
                        (" · " + r["subtype"]) if r.get("subtype") else "")
                    log_check("Text", snippet, clean, summary, r, sender)
                    # v5.5 — ALSO log the sender on the Number tab. The text
                    # check already auto-reports a scam sender to the API, so
                    # the reputation returned here is current. Logged for every
                    # band, NO REPORTS FOUND included, because "this sender is
                    # not in the table" is itself a result worth keeping.
                    snum = (sender or "").strip()
                    if snum:
                        ss["numcache"].pop(snum, None)      # force a fresh read
                        nrep = number_reputation(snum)
                        if nrep:
                            nsum = nrep.get("risk", "") + (
                                (" · " + nrep["top_type"]) if nrep.get("top_type") else "")
                            log_check("Number", snum, snum, nsum, nrep, snum)
                    st.toast("Analysis complete", icon="✅")
                    text_result_dialog(r)
                except Exception:
                    st.error("Could not reach the API. "
                             "Is `uvicorn api:app` running on port 8000?")
                # --------------------------------------------------
        st.caption("Tip: fill in the Contact Number so History can show that "
                   "sender's full scam record.")

def history_screen():
    hero("Your Check History", "Open any record for the full analysis.")
    f1, f2, f3, _, f5 = st.columns([1, 1, 1, 3, 1.4])
    for col, lab in ((f1, "All"), (f2, "Text"), (f3, "Number")):
        if col.button(lab, key=f"hf_{lab}", use_container_width=True,
                      type="primary" if ss["hist_filter"] == lab else "secondary"):
            ss["hist_filter"] = lab
            st.rerun()
    if f5.button("Clear all", key="hist_clear", use_container_width=True):
        ss["history"] = []
        _save_history(ss.get("user"), [])
        st.toast("History cleared", icon="🗑️")
        st.rerun()

    items = ss["history"] if ss["hist_filter"] == "All" else \
        [h for h in ss["history"] if h.get("type") == ss["hist_filter"]]
    st.markdown(f'<div class="sec-title" style="margin-top:12px">'
                f'{len(items)} record(s)</div>', unsafe_allow_html=True)
    render_history_rows(items, "histrow")

def account_screen():
    hero("Account", "Your A.S.E.A. profile.")
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        texts = sum(1 for h in ss["history"] if h.get("type") == "Text")
        nums = sum(1 for h in ss["history"] if h.get("type") == "Number")
        initial = (ss["name"] or "?")[0].upper()
        st.markdown(
            f'<div class="card" style="text-align:center">'
            f'<div style="width:78px;height:78px;border-radius:50%;margin:0 auto 12px;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:32px;font-weight:800;color:#fff;'
            f'background:linear-gradient(120deg,var(--accent),var(--accent-2))">'
            f'{html.escape(initial)}</div>'
            f'<h2 style="margin:0;font-size:22px">{html.escape(ss["name"])}</h2>'
            f'<p style="color:var(--muted);margin:4px 0 0">{html.escape(ss["user"])}</p>'
            f'<p style="color:var(--muted);font-size:12px;margin:8px 0 0">'
            f'Member since {html.escape(ss["since"])}</p></div>',
            unsafe_allow_html=True)
        a, b, c = st.columns(3)
        kpi_card(a, len(ss["history"]), "Total checks", "📊", 0.05)
        kpi_card(b, texts, "Texts", "💬", 0.12)
        kpi_card(c, nums, "Numbers", "☎️", 0.19)

        if st.button("Change Password", key="acct_pw",
                     use_container_width=True, type="primary"):
            # ---------- UNCHANGED Firebase logic (Step 7c) ----------
            try:
                auth.send_password_reset_email(ss["user"])
                st.success("Password reset email sent.")
            except Exception:
                st.info("Could not send reset email right now.")
            # --------------------------------------------------------

# ================= Router =================
if not ss["user"]:
    auth_screen()
else:
    page = top_nav()
    if page == "Dashboard":
        dashboard()
    elif page == "Verify Number":
        verify_number_screen()
    elif page == "Verify Text":
        verify_text_screen()
    elif page == "History":
        history_screen()
    elif page == "Account":
        account_screen()
    footer()