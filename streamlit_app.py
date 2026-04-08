import streamlit as st
from curl_cffi import requests as cfreq
import datetime, uuid
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
DIFINE_COLOR = "#fd2453"
BROMFC_COLOR = "#3B82F6"
EKIP_COLOR   = "#22C55E"

TR_FULL  = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
TR_SHORT = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

TAKIP = [
    {"isim": "Ozan Kabak",       "t_id": "2569"},
    {"isim": "Hakan Çalhanoğlu", "t_id": "2697"},
    {"isim": "Kenan Yıldız",     "t_id": "2687"},
    {"isim": "Milot Rashica",    "t_id": "3050"},
    {"isim": "Nadiem Amiri",     "t_id": "2556"},
    {"isim": "Gedson Fernandes", "t_id": "2323"},
    {"isim": "Zeki Çelik",       "t_id": "2702"},
    {"isim": "Çağlar Söyüncü",   "t_id": "3052"},
    {"isim": "Mert Müldür",      "t_id": "3052"},
    {"isim": "Kenan Karaman",    "t_id": "2530"},
    {"isim": "Can Uzun",         "t_id": "2674"},
    {"isim": "Cenk Tosun",       "t_id": "6063"},
]

# ── WEEK HELPERS ──────────────────────────────────────────────────────────────
def get_week_days():
    today = datetime.date.today()
    mon   = today - datetime.timedelta(days=today.weekday())
    return [mon + datetime.timedelta(days=i) for i in range(7)]

def get_week_id():
    return get_week_days()[0].isoformat()

def now_tr():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

# ── SESSION STATE ─────────────────────────────────────────────────────────────
if "week_id" not in st.session_state:
    st.session_state.week_id     = get_week_id()
    st.session_state.entries     = {}
    st.session_state.show_reset  = False

current_week = get_week_id()
if st.session_state.week_id != current_week:
    st.session_state.show_reset = True

# ── SOFASCORE FETCH ───────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_week_matches(week_start: str) -> dict:
    ws = datetime.date.fromisoformat(week_start)
    we = ws + datetime.timedelta(days=6)
    by_event = {}

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

    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = [exe.submit(fetch_one, t) for t in TAKIP]
        for f in as_completed(futures):
            try:
                itm, evs = f.result()
                for ev in evs:
                    try:
                        dt  = (datetime.datetime.fromtimestamp(ev["startTimestamp"], datetime.timezone.utc)
                               + datetime.timedelta(hours=3))
                        d   = dt.date()
                        if not (ws <= d <= we):
                            continue
                        eid = ev["id"]
                        if eid not in by_event:
                            st_ = ev.get("status", {}).get("type", "notstarted")
                            sh  = ev.get("homeScore", {}).get("current", "")
                            sa  = ev.get("awayScore", {}).get("current", "")
                            by_event[eid] = {
                                "date":    d.isoformat(),
                                "home":    ev.get("homeTeam", {}).get("shortName", "?"),
                                "away":    ev.get("awayTeam", {}).get("shortName", "?"),
                                "time":    dt.strftime("%H:%M"),
                                "status":  st_,
                                "score":   f"{sh}–{sa}" if st_ != "notstarted" and sh != "" else "",
                                "players": [],
                            }
                        name = itm["isim"]
                        if name not in by_event[eid]["players"]:
                            by_event[eid]["players"].append(name)
                    except:
                        pass
            except:
                pass

    result = {}
    for ev in by_event.values():
        result.setdefault(ev["date"], []).append(ev)
    return result

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');

:root {
    --bg:      #0d0d0f;
    --surface: #141418;
    --border:  rgba(255,255,255,0.07);
    --border2: rgba(255,255,255,0.13);
    --text:    #e2e8f0;
    --bright:  #f8fafc;
    --muted:   #64748b;
    --subtle:  #94a3b8;
    --green:   #22c55e;
    --red:     #fd2453;
    --blue:    #3B82F6;
    --body:    'Inter', system-ui, sans-serif;
    --mono:    'JetBrains Mono', 'Fira Code', monospace;
}

html, body, .stApp {
    background: var(--bg) !important;
    color: var(--text);
    font-family: var(--body);
}
.block-container {
    padding: 1.5rem 1.5rem 3rem !important;
    max-width: 1700px !important;
}
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebarContent"] { padding: 1.5rem 1rem; }

/* ── CALENDAR ENTRY CARDS ── */
.cal-entry {
    padding: 7px 10px;
    border-radius: 7px;
    margin-bottom: 5px;
    font-size: 0.68rem;
    line-height: 1.45;
    border-left: 3px solid;
}
.cal-entry .lbl {
    font-family: var(--mono);
    font-size: 0.55rem;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    opacity: 0.55;
    margin-bottom: 2px;
}
.cal-entry .txt { font-weight: 600; color: var(--bright); }
.cal-entry .sub { color: var(--muted); font-size: 0.62rem; margin-top: 2px; }

.ekip-e    { border-color: #22c55e; background: rgba(34,197,94,0.08); }
.difine-e  { border-color: #fd2453; background: rgba(253,36,83,0.08); }
.bromfc-e  { border-color: #3B82F6; background: rgba(59,130,246,0.08); }

/* live dot */
.live-dot {
    display: inline-block; width: 6px; height: 6px;
    border-radius: 50%; background: #fd2453;
    animation: pd 1.4s ease-in-out infinite;
    margin-left: 4px; vertical-align: middle;
}
@keyframes pd { 0%,100%{opacity:1;} 50%{opacity:0.25;} }

/* ── DAY HEADER ── */
.day-hdr {
    padding: 10px 4px 8px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
}
.day-hdr .dn {
    font-weight: 700;
    font-size: 0.75rem;
    color: var(--subtle);
}
.day-hdr .dd {
    font-family: var(--mono);
    font-size: 0.6rem;
    color: var(--muted);
    margin-top: 2px;
}
.day-hdr.today .dn { color: #3B82F6; }
.day-hdr.today .dd { color: rgba(59,130,246,0.6); }

/* ── MASTHEAD ── */
.masthead {
    font-family: var(--mono);
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 4px;
}
.masthead b { color: var(--bright); font-size: 0.88rem; }

/* ── LEGEND ── */
.legend-item {
    display: flex; align-items: center; gap: 7px;
    font-size: 0.65rem; color: var(--muted);
    margin-bottom: 5px;
}
.legend-dot {
    width: 8px; height: 8px;
    border-radius: 50%; flex-shrink: 0;
}

/* ── SIDEBAR LABELS ── */
.sidebar-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--subtle);
    margin-bottom: 6px;
    margin-top: 10px;
}

/* shrink delete button */
div[data-testid="stButton"] > button[kind="secondary"] {
    padding: 2px 6px !important;
    font-size: 0.6rem !important;
    min-height: 0 !important;
    line-height: 1 !important;
}
</style>
""", unsafe_allow_html=True)

# ── FETCH DATA ────────────────────────────────────────────────────────────────
week_days = get_week_days()
today     = datetime.date.today()
matches   = fetch_week_matches(week_days[0].isoformat())
nw        = now_tr()

# ── RESET BANNER ──────────────────────────────────────────────────────────────
if st.session_state.show_reset:
    st.warning("⚠️ **Yeni hafta başladı.** Difine ve BromFC girişleri temizlensin mi?")
    ca, cb, _ = st.columns([3, 3, 8])
    if ca.button("✓  Temizle, yeni haftaya geç", type="primary"):
        st.session_state.entries    = {}
        st.session_state.week_id    = current_week
        st.session_state.show_reset = False
        st.rerun()
    if cb.button("Daha sonra hatırlat"):
        st.session_state.show_reset = False
        st.rerun()
    st.divider()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class='masthead'><b>F41 · TAKVİM</b></div>
    <div style='font-family:var(--mono);font-size:0.6rem;color:#475569;margin-bottom:14px;'>
        Yönetim Paneli
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    # Category
    st.markdown("<div class='sidebar-label'>Kategori</div>", unsafe_allow_html=True)
    cat_choice = st.radio(
        "",
        ["🔴  Difine Media", "🔵  BromFC"],
        label_visibility="collapsed"
    )
    sel_cat   = "difine" if "Difine" in cat_choice else "bromfc"
    sel_color = DIFINE_COLOR if sel_cat == "difine" else BROMFC_COLOR

    # Day
    st.markdown("<div class='sidebar-label'>Gün</div>", unsafe_allow_html=True)
    day_opts      = [f"{TR_SHORT[i]}  ·  {week_days[i].strftime('%d %b')}" for i in range(7)]
    sel_day_label = st.selectbox("", day_opts, index=today.weekday(), label_visibility="collapsed")
    sel_day       = week_days[day_opts.index(sel_day_label)]

    # Entry text
    st.markdown("<div class='sidebar-label'>Not / Görev</div>", unsafe_allow_html=True)
    entry_text = st.text_area(
        "",
        placeholder="Reel yayını, toplantı, görev...",
        height=80,
        label_visibility="collapsed",
        key="txt_input"
    )

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

    # Legend
    st.markdown("""
    <div class='legend-item'>
        <div class='legend-dot' style='background:#22c55e;'></div>
        <span><b style='color:#22c55e;'>Ekip</b> — Otomatik (API)</span>
    </div>
    <div class='legend-item'>
        <div class='legend-dot' style='background:#fd2453;'></div>
        <span><b style='color:#fd2453;'>Difine Media</b> — Manuel</span>
    </div>
    <div class='legend-item'>
        <div class='legend-dot' style='background:#3B82F6;'></div>
        <span><b style='color:#3B82F6;'>BromFC</b> — Manuel</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style='margin-top:20px;font-family:var(--mono);font-size:0.58rem;color:#334155;'>
        Son güncelleme<br>{nw.strftime('%H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

# ── MAIN HEADER ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='display:flex;align-items:baseline;justify-content:space-between;
    padding-bottom:16px;border-bottom:1px solid rgba(255,255,255,0.07);margin-bottom:18px;'>
    <div>
        <div class='masthead'><b>F41 · HAFTALIK TAKVİM</b></div>
        <div style='font-family:var(--mono);font-size:0.68rem;color:var(--subtle);margin-top:2px;'>
            {week_days[0].strftime('%d %B')} — {week_days[6].strftime('%d %B %Y')}
        </div>
    </div>
    <div style='font-family:var(--mono);font-size:0.58rem;color:#475569;text-align:right;'>
        Otomatik yenileme · 60sn
    </div>
</div>
""", unsafe_allow_html=True)

# ── CALENDAR GRID ─────────────────────────────────────────────────────────────
cols = st.columns(7, gap="small")

for i, day in enumerate(week_days):
    is_today    = (day == today)
    d_str       = day.isoformat()
    day_matches = sorted(matches.get(d_str, []), key=lambda x: x["time"])
    day_entries = st.session_state.entries.get(d_str, [])
    today_cls   = "today" if is_today else ""

    with cols[i]:
        with st.container(border=True):

            # Day header
            st.markdown(f"""
            <div class='day-hdr {today_cls}'>
                <div class='dn'>{TR_FULL[i]}</div>
                <div class='dd'>{day.strftime('%d %b')}</div>
            </div>
            """, unsafe_allow_html=True)

            # ── Ekip matches (auto) ──────────────────────────────────────────
            for m in day_matches:
                last_names = [p.split()[-1] for p in m["players"][:3]]
                players_str = " · ".join(last_names)
                if len(m["players"]) > 3:
                    players_str += f" +{len(m['players'])-3}"
                live_dot  = "<span class='live-dot'></span>" if m["status"] == "inprogress" else ""
                score_txt = f" <b>{m['score']}</b>" if m["score"] else f" {m['time']}"
                st.markdown(f"""
                <div class='cal-entry ekip-e'>
                    <div class='lbl'>⚽ Ekip{live_dot}</div>
                    <div class='txt'>{m['home']} – {m['away']}{score_txt}</div>
                    <div class='sub'>{players_str}</div>
                </div>
                """, unsafe_allow_html=True)

            # ── Manual entries ───────────────────────────────────────────────
            to_remove = None
            for entry in list(day_entries):
                cat_class = f"{entry['cat']}-e"
                cat_label = "Difine Media" if entry["cat"] == "difine" else "BromFC"
                ec1, ec2 = st.columns([5, 1])
                with ec1:
                    st.markdown(f"""
                    <div class='cal-entry {cat_class}'>
                        <div class='lbl'>{cat_label}</div>
                        <div class='txt'>{entry['text']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with ec2:
                    if st.button("✕", key=f"del_{entry['id']}", help="Sil"):
                        to_remove = entry["id"]

            if to_remove:
                st.session_state.entries[d_str] = [
                    e for e in st.session_state.entries.get(d_str, [])
                    if e["id"] != to_remove
                ]
                st.rerun()

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center;padding:28px 0 8px;
    border-top:1px solid rgba(255,255,255,0.05);margin-top:24px;'>
    <span style='font-family:var(--mono);font-size:0.58rem;
        color:#1e293b;letter-spacing:0.12em;'>
        F41DESIGN · TAKVİM · {nw.strftime('%Y')}
    </span>
</div>
""", unsafe_allow_html=True)
