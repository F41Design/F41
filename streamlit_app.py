import streamlit as st
from curl_cffi import requests as cfreq
import datetime, uuid, base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit_autorefresh import st_autorefresh

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F41 · TAKVİM",
    layout="wide",
    page_icon="📅",
    initial_sidebar_state="expanded"
)
st_autorefresh(interval=60_000, key="cal_refresh")

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
TR_FULL  = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
TR_SHORT = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
TR_MONTHS = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",
             7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"}

TAKIP = [
    {"isim": "Ozan Kabak",       "t_id": "2569",  "p_id": "857740"},
    {"isim": "Hakan Çalhanoğlu", "t_id": "2697",  "p_id": "135700"},
    {"isim": "Kenan Yıldız",     "t_id": "2687",  "p_id": "1149011"},
    {"isim": "Milot Rashica",    "t_id": "3050",  "p_id": "800411"},
    {"isim": "Nadiem Amiri",     "t_id": "2556",  "p_id": "327755"},
    {"isim": "Gedson Fernandes", "t_id": "2323",  "p_id": "862055"},
    {"isim": "Zeki Çelik",       "t_id": "2702",  "p_id": "893008"},
    {"isim": "Çağlar Söyüncü",   "t_id": "3052",  "p_id": "758608"},
    {"isim": "Mert Müldür",      "t_id": "3052",  "p_id": "836683"},
    {"isim": "Kenan Karaman",    "t_id": "2530",  "p_id": "168943"},
    {"isim": "Can Uzun",         "t_id": "2674",  "p_id": "1440948"},
    {"isim": "Cenk Tosun",       "t_id": "6063",  "p_id": "72127"},
]
PLAYER_IDS = {t["isim"]: t["p_id"] for t in TAKIP}

# ── WEEK HELPERS ──────────────────────────────────────────────────────────────
def get_week_days():
    today = datetime.date.today()
    mon   = today - datetime.timedelta(days=today.weekday())
    return [mon + datetime.timedelta(days=i) for i in range(7)]

def get_week_id():
    return get_week_days()[0].isoformat()

def now_tr():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

def fmt_date_tr(d):
    return f"{d.day} {TR_MONTHS[d.month]}"

# ── SESSION STATE ─────────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "week_id":        get_week_id(),
        "entries":        {},
        "show_reset":     False,
        "search_results": [],
        "search_matches": [],
        "search_entity":  None,
        "photos":         {},
        "photos_loaded":  False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

current_week = get_week_id()
if st.session_state.week_id != current_week:
    st.session_state.show_reset = True

# ── PLAYER PHOTOS ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_photo_b64(p_id: str) -> str:
    """Single player photo, cached 24h globally."""
    try:
        r = cfreq.get(
            f"https://api.sofascore.app/api/v1/player/{p_id}/image",
            headers={"Referer": "https://www.sofascore.com/"},
            impersonate="chrome110", timeout=6
        )
        if r.status_code == 200:
            return f"data:image/png;base64,{base64.b64encode(r.content).decode()}"
    except:
        pass
    return ""

def preload_photos():
    """Load all photos once per session into session_state."""
    if st.session_state.photos_loaded:
        return
    def one(itm):
        return itm["isim"], _fetch_photo_b64(itm["p_id"])
    with ThreadPoolExecutor(max_workers=10) as exe:
        for f in as_completed([exe.submit(one, t) for t in TAKIP]):
            try:
                name, photo = f.result()
                st.session_state.photos[name] = photo
            except:
                pass
    st.session_state.photos_loaded = True

preload_photos()

def player_chips_html(player_names: list) -> str:
    """Returns stacked avatar chips HTML for given player names."""
    chips = ""
    for name in player_names[:4]:
        src = st.session_state.photos.get(name, "")
        if src:
            short = name.split()[-1]
            chips += f"<img class='p-chip' src='{src}' title='{name}' alt='{short}'>"
        else:
            initials = "".join(p[0] for p in name.split()[:2])
            chips += f"<div class='p-chip p-chip-fallback' title='{name}'>{initials}</div>"
    extra = len(player_names) - 4
    if extra > 0:
        chips += f"<div class='p-chip p-chip-extra'>+{extra}</div>"
    return f"<div class='p-chips'>{chips}</div>"

# ── SOFASCORE: AUTO MATCHES ───────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_week_matches(week_start: str) -> dict:
    ws = datetime.date.fromisoformat(week_start)
    we = ws + datetime.timedelta(days=6)
    by_event: dict = {}

    def fetch_one(itm):
        evs = []
        for path in ["next", "last"]:
            try:
                r = cfreq.get(
                    f"https://api.sofascore.com/api/v1/team/{itm['t_id']}/events/{path}/0",
                    impersonate="chrome110", timeout=8
                ).json()
                evs.extend(r.get("events", []))
            except:
                pass
        return itm, evs

    with ThreadPoolExecutor(max_workers=10) as exe:
        for f in as_completed([exe.submit(fetch_one, t) for t in TAKIP]):
            try:
                itm, evs = f.result()
                for ev in evs:
                    try:
                        dt  = (datetime.datetime.fromtimestamp(
                                   ev["startTimestamp"], datetime.timezone.utc)
                               + datetime.timedelta(hours=3))
                        d   = dt.date()
                        if not (ws <= d <= we):
                            continue
                        eid = ev["id"]
                        st_ = ev.get("status", {}).get("type", "notstarted")
                        sh  = ev.get("homeScore", {}).get("current", "")
                        sa  = ev.get("awayScore", {}).get("current", "")
                        score = f"{sh}–{sa}" if st_ != "notstarted" and sh != "" else ""
                        if eid not in by_event:
                            by_event[eid] = {
                                "date":    d.isoformat(),
                                "home":    ev.get("homeTeam", {}).get("shortName", "?"),
                                "away":    ev.get("awayTeam", {}).get("shortName", "?"),
                                "time":    dt.strftime("%H:%M"),
                                "status":  st_,
                                "score":   score,
                                "players": [],
                            }
                        else:
                            by_event[eid]["status"] = st_
                            if score:
                                by_event[eid]["score"] = score
                        if itm["isim"] not in by_event[eid]["players"]:
                            by_event[eid]["players"].append(itm["isim"])
                    except:
                        pass
            except:
                pass

    result: dict = {}
    for ev in by_event.values():
        result.setdefault(ev["date"], []).append(ev)
    return result

# ── SOFASCORE: SEARCH ─────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def sofa_search(query: str):
    try:
        r = cfreq.get(
            f"https://api.sofascore.com/api/v1/search/all/?q={query}",
            impersonate="chrome110", timeout=8
        ).json()
        results = []
        for item in r.get("results", [])[:15]:
            entity = item.get("entity", {})
            t      = item.get("type", "")
            sport  = (entity.get("sport") or {}).get("slug", "")
            if t == "player" and sport == "football":
                team = entity.get("team", {})
                results.append({
                    "type":   "player",
                    "label":  f"👤 {entity.get('name','')}",
                    "name":   entity.get("name", ""),
                    "t_id":   str(team.get("id", "")),
                    "t_name": team.get("shortName", team.get("name", "")),
                })
            elif t == "team" and sport == "football":
                results.append({
                    "type":   "team",
                    "label":  f"🏟 {entity.get('name','')}",
                    "name":   entity.get("name", ""),
                    "t_id":   str(entity.get("id", "")),
                    "t_name": entity.get("shortName", entity.get("name", "")),
                })
        return results[:8]
    except:
        return []

@st.cache_data(ttl=120, show_spinner=False)
def get_team_matches_this_week(t_id: str, week_start: str):
    ws = datetime.date.fromisoformat(week_start)
    we = ws + datetime.timedelta(days=6)
    seen: dict = {}
    for path in ["next", "last"]:
        try:
            r = cfreq.get(
                f"https://api.sofascore.com/api/v1/team/{t_id}/events/{path}/0",
                impersonate="chrome110", timeout=8
            ).json()
            for ev in r.get("events", []):
                dt = (datetime.datetime.fromtimestamp(
                          ev["startTimestamp"], datetime.timezone.utc)
                      + datetime.timedelta(hours=3))
                d = dt.date()
                if ws <= d <= we:
                    st_ = ev.get("status", {}).get("type", "notstarted")
                    sh  = ev.get("homeScore", {}).get("current", "")
                    sa  = ev.get("awayScore", {}).get("current", "")
                    seen[ev["id"]] = {
                        "date":     d.isoformat(),
                        "day":      TR_FULL[d.weekday()],
                        "home":     ev.get("homeTeam", {}).get("shortName", "?"),
                        "away":     ev.get("awayTeam", {}).get("shortName", "?"),
                        "time":     dt.strftime("%H:%M"),
                        "status":   st_,
                        "score":    f"{sh}–{sa}" if st_ != "notstarted" and sh != "" else "",
                        "event_id": ev["id"],
                    }
        except:
            pass
    return sorted(seen.values(), key=lambda x: x["date"])

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
    --bg:      #08080f;
    --surface: #0d0d16;
    --s2:      #12121c;
    --border:  rgba(255,255,255,0.06);
    --border2: rgba(255,255,255,0.11);
    --text:    #bcc8dc;
    --bright:  #edf2f8;
    --muted:   #424f63;
    --subtle:  #667080;
    --green:   #22c55e;
    --red:     #fd2453;
    --blue:    #3B82F6;
    --amber:   #f59e0b;
    --body:    'Inter', system-ui, sans-serif;
    --mono:    'JetBrains Mono', monospace;
}
html, body, .stApp { background: var(--bg) !important; color: var(--text); font-family: var(--body); }
.block-container { padding: 0 1.4rem 3rem !important; max-width: 1800px !important; }
[data-testid="stSidebar"] { background: var(--surface) !important; border-right: 1px solid var(--border) !important; }
[data-testid="stSidebarContent"] { padding: 1.4rem 1rem; }

/* ── MASTHEAD ── */
.masthead-wrap {
    display:flex; align-items:center; justify-content:space-between;
    padding:22px 0 15px; border-bottom:1px solid var(--border); margin-bottom:12px;
}
.mh-title { font-family:var(--mono); font-size:0.63rem; font-weight:700;
    letter-spacing:0.25em; text-transform:uppercase; color:var(--subtle); }
.mh-title b { color:var(--bright); font-size:1.1rem; letter-spacing:0.1em; }
.mh-sub  { font-family:var(--mono); font-size:0.6rem; color:var(--muted); margin-top:3px; }
.mh-right { font-family:var(--mono); font-size:0.57rem; color:var(--muted); text-align:right; line-height:1.85; }
.mh-right span { color:var(--subtle); }

/* ── SUMMARY STRIP ── */
.summary-strip { display:flex; gap:5px; padding:8px 0 15px; flex-wrap:wrap; }
.sp {
    display:inline-flex; align-items:center; gap:6px; padding:5px 12px;
    border-radius:100px; border:1px solid; font-family:var(--mono);
    font-size:0.6rem; font-weight:700; letter-spacing:0.06em; white-space:nowrap;
}
.sp-m { color:#22c55e; border-color:rgba(34,197,94,.22); background:rgba(34,197,94,.07); }
.sp-d { color:#fd2453; border-color:rgba(253,36,83,.22);  background:rgba(253,36,83,.07); }
.sp-b { color:#3B82F6; border-color:rgba(59,130,246,.22); background:rgba(59,130,246,.07); }
.sp-l { color:#fd2453; border-color:rgba(253,36,83,.4);   background:rgba(253,36,83,.1);
    animation:ppulse 2s ease-in-out infinite; }
@keyframes ppulse { 0%,100%{box-shadow:0 0 0 0 rgba(253,36,83,.3);} 50%{box-shadow:0 0 0 5px rgba(253,36,83,0);} }
.sp-dot { width:5px; height:5px; border-radius:50%; background:currentColor; flex-shrink:0; }

/* ── DAY HEADER ── */
.day-hdr { padding:9px 11px 9px; border-bottom:1px solid var(--border); margin-bottom:7px; }
.dh-name { font-weight:700; font-size:0.7rem; color:var(--subtle); }
.dh-date { font-family:var(--mono); font-size:0.56rem; color:var(--muted); margin-top:2px; }
.dh-today .dh-name { color:var(--blue); }
.dh-today .dh-date { color:rgba(59,130,246,.5); }
.today-pip {
    display:inline-block; width:5px; height:5px; border-radius:50%;
    background:var(--blue); margin-left:5px; vertical-align:middle;
    animation:pip 2s ease-in-out infinite;
}
@keyframes pip { 0%,100%{opacity:1;} 50%{opacity:0.2;} }

/* ── ENTRY CARDS ── */
.cal-entry {
    padding:7px 9px 8px; border-radius:7px; margin-bottom:4px;
    border-left:2.5px solid; font-size:0.66rem; line-height:1.45;
}
.e-lbl {
    font-family:var(--mono); font-size:0.5rem; letter-spacing:0.1em;
    text-transform:uppercase; margin-bottom:3px; opacity:0.48;
    display:flex; align-items:center; gap:5px;
}
.e-txt { font-weight:600; color:var(--bright); font-size:0.68rem; }
.e-sub { color:var(--muted); font-size:0.58rem; margin-top:3px; }
.e-ekip         { border-color:#22c55e; background:rgba(34,197,94,.07); }
.e-difine       { border-color:#fd2453; background:rgba(253,36,83,.07); }
.e-bromfc       { border-color:#3B82F6; background:rgba(59,130,246,.07); }
.e-manual-match { border-color:#22c55e; background:rgba(34,197,94,.07); }

/* ── PLAYER CHIPS ── */
.p-chips { display:flex; align-items:center; margin-top:5px; }
.p-chip {
    width:22px; height:22px; border-radius:50%; object-fit:cover;
    border:1.5px solid rgba(34,197,94,.35); margin-right:-5px;
    background:var(--s2); flex-shrink:0;
    transition:transform .15s;
}
.p-chip:hover { transform:scale(1.15); z-index:1; }
.p-chip-fallback {
    width:22px; height:22px; border-radius:50%;
    background:var(--s2); border:1.5px solid var(--border2);
    display:inline-flex; align-items:center; justify-content:center;
    font-family:var(--mono); font-size:0.45rem; font-weight:700;
    color:var(--subtle); margin-right:-5px; flex-shrink:0;
}
.p-chip-extra {
    width:22px; height:22px; border-radius:50%;
    background:var(--s2); border:1.5px solid var(--border2);
    display:inline-flex; align-items:center; justify-content:center;
    font-family:var(--mono); font-size:0.45rem; color:var(--muted);
    margin-right:-5px; flex-shrink:0;
}

/* ── BADGES ── */
.badge {
    display:inline-flex; align-items:center; gap:3px; padding:1px 5px;
    border-radius:4px; font-family:var(--mono); font-size:0.49rem;
    font-weight:700; letter-spacing:0.05em; vertical-align:middle;
}
.b-live { color:#fd2453; background:rgba(253,36,83,.12); border:1px solid rgba(253,36,83,.3);
    animation:blk 1.4s ease-in-out infinite; }
@keyframes blk { 0%,100%{opacity:1;} 50%{opacity:0.35;} }
.b-done { color:#22c55e; background:rgba(34,197,94,.1); border:1px solid rgba(34,197,94,.22); }
.b-soon { color:#f59e0b; background:rgba(245,158,11,.1); border:1px solid rgba(245,158,11,.22); }
.live-score { font-family:var(--mono); font-weight:700; color:var(--bright); font-size:0.7rem; }

/* ── SIDEBAR ── */
.sb-title { font-family:var(--mono); font-size:0.56rem; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); }
.sb-title b { color:var(--bright); font-size:0.78rem; }
.sb-lbl { font-family:var(--mono); font-size:0.57rem; font-weight:700;
    letter-spacing:0.12em; text-transform:uppercase; color:var(--muted);
    margin-bottom:6px; margin-top:12px; }
.leg-row { display:flex; align-items:center; gap:7px; font-size:0.61rem; color:var(--muted); margin-bottom:5px; }
.leg-pip { width:7px; height:7px; border-radius:2px; flex-shrink:0; }

/* streamlit overrides */
div[data-testid="stButton"]>button {
    font-family:var(--mono)!important; font-size:0.62rem!important;
    letter-spacing:0.04em; padding:4px 10px!important;
}
div[data-testid="stRadio"] label { font-size:0.7rem!important; }
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background:var(--s2)!important; border-color:var(--border2)!important;
    color:var(--text)!important; font-size:0.7rem!important;
}
div[data-testid="stSelectbox"]>div>div {
    background:var(--s2)!important; border-color:var(--border2)!important; font-size:0.7rem!important;
}
/* tiny reorder/delete buttons */
.btn-tiny > div[data-testid="stButton"] > button {
    padding:2px 5px!important; font-size:0.55rem!important;
    min-height:0!important; line-height:1.2!important;
    background:transparent!important; border-color:var(--border2)!important;
    color:var(--muted)!important;
}
.btn-tiny > div[data-testid="stButton"] > button:hover {
    color:var(--bright)!important; border-color:var(--border2)!important;
}
</style>
""", unsafe_allow_html=True)

# ── DATA ──────────────────────────────────────────────────────────────────────
week_days    = get_week_days()
today        = datetime.date.today()
auto_matches = fetch_week_matches(week_days[0].isoformat())
nw           = now_tr()

# ── RESET BANNER ──────────────────────────────────────────────────────────────
if st.session_state.show_reset:
    st.warning("⚠️ **Yeni hafta başladı.** Difine ve BromFC girişleri temizlensin mi?")
    ca, cb, _ = st.columns([3, 3, 8])
    if ca.button("✓  Temizle, yeni haftaya geç", type="primary"):
        st.session_state.entries    = {}
        st.session_state.week_id    = current_week
        st.session_state.show_reset = False
        st.rerun()
    if cb.button("Daha sonra"):
        st.session_state.show_reset = False
        st.rerun()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class='sb-title'><b>F41 · TAKVİM</b></div>
    <div style='font-family:var(--mono);font-size:0.52rem;color:#1e293b;letter-spacing:0.1em;margin-bottom:10px;'>
        YÖNETİM PANELİ
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    st.markdown("<div class='sb-lbl'>Kategori</div>", unsafe_allow_html=True)
    cat_choice = st.radio("", ["🔴  Difine Media", "🔵  BromFC", "🟢  Futbol (Manuel)"],
                          label_visibility="collapsed", key="cat_radio")
    sel_cat = ("difine" if "Difine" in cat_choice
               else "bromfc" if "BromFC" in cat_choice
               else "futbol")

    st.markdown("<div class='sb-lbl'>Gün</div>", unsafe_allow_html=True)
    day_opts      = [f"{TR_SHORT[i]}  ·  {week_days[i].strftime('%d %b')}" for i in range(7)]
    sel_day_label = st.selectbox("", day_opts, index=today.weekday(), label_visibility="collapsed")
    sel_day       = week_days[day_opts.index(sel_day_label)]

    # ── FUTBOL SEARCH ────────────────────────────────────────────────────────
    if sel_cat == "futbol":
        st.markdown("<div class='sb-lbl'>Takım / Oyuncu Ara</div>", unsafe_allow_html=True)
        search_q = st.text_input("", placeholder="örn: Galatasaray, Mbappé...",
                                 label_visibility="collapsed", key="search_input")
        if st.button("🔍  Ara", use_container_width=True):
            if search_q.strip():
                with st.spinner("Aranıyor..."):
                    st.session_state.search_results = sofa_search(search_q.strip())
                    st.session_state.search_entity  = None
                    st.session_state.search_matches  = []

        if st.session_state.search_results:
            st.markdown("<div class='sb-lbl'>Sonuçlar</div>", unsafe_allow_html=True)
            for idx, res in enumerate(st.session_state.search_results):
                lbl = (f"{res['label']} · {res['t_name']}"
                       if res["type"] == "player" else res["label"])
                if st.button(lbl, key=f"sr_{idx}", use_container_width=True):
                    with st.spinner("Maçlar yükleniyor..."):
                        mlist = get_team_matches_this_week(res["t_id"], week_days[0].isoformat())
                        st.session_state.search_matches = mlist
                        st.session_state.search_entity  = res
                        st.session_state.search_results = []

        if st.session_state.search_matches:
            entity = st.session_state.search_entity or {}
            st.markdown(f"<div class='sb-lbl'>{entity.get('name','')} — Bu Hafta</div>",
                        unsafe_allow_html=True)
            if not st.session_state.search_matches:
                st.caption("Bu hafta maç bulunamadı.")
            for midx, m in enumerate(st.session_state.search_matches):
                score_txt = f" {m['score']}" if m["score"] else f" {m['time']}"
                icon = ("🔴" if m["status"] == "inprogress"
                        else "✅" if m["status"] == "finished" else "📅")
                btn_lbl = f"{icon} {m['day'][:3]} · {m['home']} – {m['away']}{score_txt}"
                if st.button(btn_lbl, key=f"madd_{midx}", use_container_width=True, type="primary"):
                    d = m["date"]
                    st.session_state.entries.setdefault(d, []).append({
                        "cat":    "manual_match",
                        "text":   f"{m['home']} – {m['away']}",
                        "sub":    f"{m['time']} · {entity.get('name','')}",
                        "time":   m["time"],
                        "status": m["status"],
                        "score":  m.get("score", ""),
                        "id":     uuid.uuid4().hex[:8],
                    })
                    st.session_state.search_matches = []
                    st.session_state.search_entity  = None
                    st.rerun()

    # ── DIFINE / BROMFC ──────────────────────────────────────────────────────
    else:
        st.markdown("<div class='sb-lbl'>Not / Görev</div>", unsafe_allow_html=True)
        entry_text = st.text_area("", placeholder="Reel, toplantı, görev...",
                                  height=80, label_visibility="collapsed", key="txt_input")
        if st.button("➕  Takvime Ekle", use_container_width=True, type="primary"):
            if entry_text.strip():
                d = sel_day.isoformat()
                st.session_state.entries.setdefault(d, []).append({
                    "cat":  sel_cat,
                    "text": entry_text.strip(),
                    "id":   uuid.uuid4().hex[:8],
                })
                st.rerun()

    st.divider()
    st.markdown("""
    <div class='leg-row'><div class='leg-pip' style='background:#22c55e;'></div>
        <span><b style='color:#22c55e;'>Ekip & Futbol</b></span></div>
    <div class='leg-row'><div class='leg-pip' style='background:#fd2453;'></div>
        <span><b style='color:#fd2453;'>Difine Media</b></span></div>
    <div class='leg-row'><div class='leg-pip' style='background:#3B82F6;'></div>
        <span><b style='color:#3B82F6;'>BromFC</b></span></div>
    """, unsafe_allow_html=True)
    st.markdown(f"""
    <div style='margin-top:14px;font-family:var(--mono);font-size:0.51rem;color:#111827;'>
        {nw.strftime('%H:%M:%S')} · 60sn yenileme
    </div>""", unsafe_allow_html=True)

# ── SUMMARY COUNTS ────────────────────────────────────────────────────────────
total_matches = sum(len(v) for v in auto_matches.values())
for entries in st.session_state.entries.values():
    total_matches += sum(1 for e in entries if e.get("cat") == "manual_match")
total_difine = sum(
    sum(1 for e in v if e.get("cat") == "difine")
    for v in st.session_state.entries.values()
)
total_bromfc = sum(
    sum(1 for e in v if e.get("cat") == "bromfc")
    for v in st.session_state.entries.values()
)
live_count = sum(
    sum(1 for m in v if m.get("status") == "inprogress")
    for v in auto_matches.values()
)
for entries in st.session_state.entries.values():
    live_count += sum(1 for e in entries
                      if e.get("cat") == "manual_match" and e.get("status") == "inprogress")

# ── MAIN HEADER ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='masthead-wrap'>
    <div>
        <div class='mh-title'><b>F41 · TAKVİM</b></div>
        <div class='mh-sub'>
            {fmt_date_tr(week_days[0])} — {fmt_date_tr(week_days[6])} {week_days[6].year}
        </div>
    </div>
    <div class='mh-right'>
        <span>{TR_FULL[nw.weekday()]}, {fmt_date_tr(nw.date())} {nw.year}</span><br>
        {nw.strftime('%H:%M')}
    </div>
</div>
""", unsafe_allow_html=True)

# Summary strip
live_pill = (f"<div class='sp sp-l'><div class='sp-dot'></div>{live_count} CANLI</div>"
             if live_count > 0 else "")
st.markdown(f"""
<div class='summary-strip'>
    <div class='sp sp-m'><div class='sp-dot'></div>{total_matches} Maç</div>
    <div class='sp sp-d'><div class='sp-dot'></div>{total_difine} Difine</div>
    <div class='sp sp-b'><div class='sp-dot'></div>{total_bromfc} BromFC</div>
    {live_pill}
</div>
""", unsafe_allow_html=True)

# ── CALENDAR GRID ─────────────────────────────────────────────────────────────
cols = st.columns(7, gap="small")

for i, day in enumerate(week_days):
    is_today = (day == today)
    is_past  = (day < today)
    d_str    = day.isoformat()

    day_matches = sorted(auto_matches.get(d_str, []), key=lambda x: x["time"])
    day_entries = st.session_state.entries.get(d_str, [])

    opacity    = "0.32" if is_past else ("1.0" if is_today else "0.8")
    today_cls  = "dh-today" if is_today else ""
    today_dot  = "<span class='today-pip'></span>" if is_today else ""

    with cols[i]:
        with st.container(border=True):
            st.markdown(f"<div style='opacity:{opacity};transition:opacity .15s;'>",
                        unsafe_allow_html=True)

            # Day header
            st.markdown(f"""
            <div class='day-hdr {today_cls}'>
                <div class='dh-name'>{TR_FULL[i]}{today_dot}</div>
                <div class='dh-date'>{day.strftime('%d %b')}</div>
            </div>
            """, unsafe_allow_html=True)

            # ── Auto Ekip matches ────────────────────────────────────────────
            for m in day_matches:
                chips_html = player_chips_html(m["players"])

                if m["status"] == "inprogress":
                    badge      = "<span class='badge b-live'>● CANLI</span>"
                    score_part = (f" <span class='live-score'>{m['score']}</span>"
                                  if m["score"] else "")
                elif m["status"] == "finished":
                    badge      = "<span class='badge b-done'>MS</span>"
                    score_part = f" <b>{m['score']}</b>" if m["score"] else ""
                else:
                    badge = ""
                    score_part = f" {m['time']}"
                    try:
                        match_dt = datetime.datetime.strptime(
                            f"{d_str} {m['time']}", "%Y-%m-%d %H:%M")
                        diff_min = (match_dt - nw.replace(tzinfo=None)).total_seconds() / 60
                        if 0 < diff_min <= 180:
                            h  = int(diff_min // 60)
                            mn = int(diff_min % 60)
                            t  = f"{h}s {mn}dk" if h > 0 else f"{mn}dk"
                            badge = f"<span class='badge b-soon'>{t} kaldı</span>"
                    except:
                        pass

                st.markdown(f"""
                <div class='cal-entry e-ekip'>
                    <div class='e-lbl'>⚽ Ekip {badge}</div>
                    <div class='e-txt'>{m['home']} – {m['away']}{score_part}</div>
                    {chips_html}
                </div>
                """, unsafe_allow_html=True)

            # ── Manual entries with ↑↓ reorder ──────────────────────────────
            action = None  # ("remove"|"up"|"down", entry_id)

            for j, entry in enumerate(list(day_entries)):
                cat = entry.get("cat", "difine")

                # Build card HTML
                if cat == "manual_match":
                    status     = entry.get("status", "notstarted")
                    score      = entry.get("score", "")
                    if status == "inprogress":
                        badge      = "<span class='badge b-live'>● CANLI</span>"
                        score_part = (f" <span class='live-score'>{score}</span>"
                                      if score else "")
                    elif status == "finished":
                        badge      = "<span class='badge b-done'>MS</span>"
                        score_part = f" <b>{score}</b>" if score else ""
                    else:
                        badge = ""
                        score_part = f" {entry.get('time','')}"
                    card_html = f"""
                    <div class='cal-entry e-manual-match'>
                        <div class='e-lbl'>⚽ Manuel {badge}</div>
                        <div class='e-txt'>{entry['text']}{score_part}</div>
                        <div class='e-sub'>{entry.get('sub','')}</div>
                    </div>"""
                else:
                    cat_cls   = f"e-{cat}"
                    cat_label = "Difine Media" if cat == "difine" else "BromFC"
                    card_html = f"""
                    <div class='cal-entry {cat_cls}'>
                        <div class='e-lbl'>{cat_label}</div>
                        <div class='e-txt'>{entry['text']}</div>
                    </div>"""

                # Render card + tiny control buttons
                st.markdown(card_html, unsafe_allow_html=True)

                # Control row: ↑  ↓  ✕  (tiny, inline)
                n = len(day_entries)
                b_cols = st.columns([1, 1, 1, 5])
                with st.container():
                    st.markdown('<div class="btn-tiny">', unsafe_allow_html=True)
                    with b_cols[0]:
                        up_disabled = (j == 0)
                        if st.button("↑", key=f"up_{entry['id']}",
                                     disabled=up_disabled, help="Yukarı"):
                            action = ("up", entry["id"], j)
                    with b_cols[1]:
                        dn_disabled = (j == n - 1)
                        if st.button("↓", key=f"dn_{entry['id']}",
                                     disabled=dn_disabled, help="Aşağı"):
                            action = ("down", entry["id"], j)
                    with b_cols[2]:
                        if st.button("✕", key=f"del_{entry['id']}", help="Sil"):
                            action = ("remove", entry["id"], j)
                    st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)  # opacity wrapper

            # Apply action after loop (avoids mid-render mutation)
            if action:
                act, eid, idx = action
                elist = st.session_state.entries.get(d_str, [])
                if act == "remove":
                    st.session_state.entries[d_str] = [e for e in elist if e["id"] != eid]
                elif act == "up" and idx > 0:
                    elist[idx], elist[idx - 1] = elist[idx - 1], elist[idx]
                    st.session_state.entries[d_str] = elist
                elif act == "down" and idx < len(elist) - 1:
                    elist[idx], elist[idx + 1] = elist[idx + 1], elist[idx]
                    st.session_state.entries[d_str] = elist
                st.rerun()

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center;padding:28px 0 8px;
    border-top:1px solid rgba(255,255,255,0.04);margin-top:22px;'>
    <span style='font-family:var(--mono);font-size:0.52rem;color:#0f172a;letter-spacing:0.14em;text-transform:uppercase;'>
        F41DESIGN · TAKVİM · {nw.strftime('%Y')}
    </span>
</div>
""", unsafe_allow_html=True)
