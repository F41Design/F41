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
    st.session_state.week_id    = get_week_id()
    st.session_state.entries    = {}
    st.session_state.show_reset = False

if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "search_matches" not in st.session_state:
    st.session_state.search_matches = []
if "search_entity" not in st.session_state:
    st.session_state.search_entity = None

current_week = get_week_id()
if st.session_state.week_id != current_week:
    st.session_state.show_reset = True

# ── SOFASCORE: AUTO FETCH ─────────────────────────────────────────────────────
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
                        if eid not in by_event:
                            by_event[eid] = {
                                "date":    d.isoformat(),
                                "home":    ev.get("homeTeam", {}).get("shortName", "?"),
                                "away":    ev.get("awayTeam", {}).get("shortName", "?"),
                                "time":    dt.strftime("%H:%M"),
                                "status":  st_,
                                "score":   f"{sh}–{sa}" if st_ != "notstarted" and sh != "" else "",
                                "players": [],
                            }
                        else:
                            by_event[eid]["status"] = st_
                            if st_ != "notstarted" and sh != "":
                                by_event[eid]["score"] = f"{sh}–{sa}"
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
def get_team_next_matches(t_id: str, week_start: str):
    ws = datetime.date.fromisoformat(week_start)
    we = ws + datetime.timedelta(days=6)
    seen = {}
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
                d  = dt.date()
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
    --bg:      #080810;
    --surface: #0e0e16;
    --s2:      #13131c;
    --border:  rgba(255,255,255,0.06);
    --border2: rgba(255,255,255,0.11);
    --text:    #c4cdd e;
    --bright:  #edf2f8;
    --muted:   #4a5568;
    --subtle:  #718096;
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
    display: flex; align-items: center; justify-content: space-between;
    padding: 22px 0 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
}
.masthead-title {
    font-family: var(--mono); font-size: 0.65rem; font-weight: 700;
    letter-spacing: 0.25em; text-transform: uppercase; color: var(--subtle);
}
.masthead-title b { color: var(--bright); font-size: 1.1rem; letter-spacing: 0.1em; }
.masthead-sub { font-family: var(--mono); font-size: 0.62rem; color: var(--muted); margin-top: 3px; }
.masthead-right { font-family: var(--mono); font-size: 0.58rem; color: var(--muted); text-align: right; line-height: 1.8; }
.masthead-right span { color: var(--subtle); }

/* ── SUMMARY STRIP ── */
.summary-strip { display: flex; gap: 6px; padding: 10px 0 16px; flex-wrap: wrap; }
.summary-pill {
    display: inline-flex; align-items: center; gap: 7px;
    padding: 6px 13px; border-radius: 100px; border: 1px solid;
    font-family: var(--mono); font-size: 0.62rem; font-weight: 700;
    letter-spacing: 0.06em; white-space: nowrap;
}
.sp-matches { color:#22c55e; border-color:rgba(34,197,94,.25); background:rgba(34,197,94,.07); }
.sp-difine  { color:#fd2453; border-color:rgba(253,36,83,.25);  background:rgba(253,36,83,.07); }
.sp-bromfc  { color:#3B82F6; border-color:rgba(59,130,246,.25); background:rgba(59,130,246,.07); }
.sp-live    { color:#fd2453; border-color:rgba(253,36,83,.4);   background:rgba(253,36,83,.1);
    animation: ppulse 2s ease-in-out infinite; }
@keyframes ppulse { 0%,100%{box-shadow:0 0 0 0 rgba(253,36,83,.3);} 50%{box-shadow:0 0 0 5px rgba(253,36,83,0);} }
.sp-dot { width:6px; height:6px; border-radius:50%; background:currentColor; flex-shrink:0; }

/* ── DAY COLUMN ── */
.day-header { padding: 9px 11px 9px; border-bottom: 1px solid var(--border); margin-bottom: 7px; }
.dh-name { font-weight: 700; font-size: 0.72rem; color: var(--subtle); letter-spacing: 0.01em; }
.dh-date { font-family: var(--mono); font-size: 0.57rem; color: var(--muted); margin-top: 2px; }
.dh-today .dh-name { color: var(--blue); }
.dh-today .dh-date { color: rgba(59,130,246,.55); }
.today-pip {
    display: inline-block; width: 5px; height: 5px; border-radius: 50%;
    background: var(--blue); margin-left: 5px; vertical-align: middle;
    animation: pip 2s ease-in-out infinite;
}
@keyframes pip { 0%,100%{opacity:1;} 50%{opacity:0.25;} }

/* ── ENTRY CARDS ── */
.cal-entry {
    padding: 7px 9px 8px; border-radius: 7px; margin-bottom: 5px;
    border-left: 2.5px solid; font-size: 0.67rem; line-height: 1.45;
}
.e-lbl {
    font-family: var(--mono); font-size: 0.52rem; letter-spacing: 0.1em;
    text-transform: uppercase; margin-bottom: 3px; opacity: 0.5;
    display: flex; align-items: center; gap: 5px;
}
.e-txt { font-weight: 600; color: var(--bright); font-size: 0.69rem; }
.e-sub { color: var(--muted); font-size: 0.59rem; margin-top: 3px; }

.e-ekip         { border-color:#22c55e; background:rgba(34,197,94,.07); }
.e-difine       { border-color:#fd2453; background:rgba(253,36,83,.07); }
.e-bromfc       { border-color:#3B82F6; background:rgba(59,130,246,.07); }
.e-manual-match { border-color:#22c55e; background:rgba(34,197,94,.07); }

/* badges */
.badge {
    display:inline-flex; align-items:center; gap:3px;
    padding:1px 5px; border-radius:4px;
    font-family:var(--mono); font-size:0.5rem; font-weight:700; letter-spacing:0.05em;
    vertical-align:middle;
}
.b-live { color:#fd2453; background:rgba(253,36,83,.12); border:1px solid rgba(253,36,83,.3);
    animation:blk 1.4s ease-in-out infinite; }
@keyframes blk { 0%,100%{opacity:1;} 50%{opacity:0.4;} }
.b-done { color:#22c55e; background:rgba(34,197,94,.1); border:1px solid rgba(34,197,94,.25); }
.b-soon { color:#f59e0b; background:rgba(245,158,11,.1); border:1px solid rgba(245,158,11,.25); }

.live-score { font-family:var(--mono); font-weight:700; color:var(--bright); font-size:0.73rem; }

/* ── SIDEBAR ── */
.sb-label {
    font-family:var(--mono); font-size:0.58rem; font-weight:700;
    letter-spacing:0.12em; text-transform:uppercase; color:var(--muted);
    margin-bottom:7px; margin-top:14px;
}
.sb-title { font-family:var(--mono); font-size:0.57rem; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); }
.sb-title b { color:var(--bright); font-size:0.8rem; }
.legend-row { display:flex; align-items:center; gap:7px; font-size:0.62rem; color:var(--muted); margin-bottom:5px; }
.legend-pip { width:7px; height:7px; border-radius:2px; flex-shrink:0; }

/* streamlit overrides */
div[data-testid="stButton"]>button { font-family:var(--mono)!important; font-size:0.64rem!important; letter-spacing:0.04em; }
div[data-testid="stRadio"] label { font-size:0.71rem!important; }
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea { background:var(--s2)!important; border-color:var(--border2)!important; color:var(--text)!important; font-size:0.71rem!important; }
div[data-testid="stSelectbox"]>div>div { background:var(--s2)!important; border-color:var(--border2)!important; font-size:0.71rem!important; }
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
    <div style='font-family:var(--mono);font-size:0.54rem;color:#2d3748;letter-spacing:0.1em;margin-bottom:10px;'>
        YÖNETİM PANELİ
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    # Category
    st.markdown("<div class='sb-label'>Kategori</div>", unsafe_allow_html=True)
    cat_choice = st.radio("", ["🔴  Difine Media", "🔵  BromFC", "🟢  Futbol (Manuel)"],
                          label_visibility="collapsed", key="cat_radio")
    sel_cat = "difine" if "Difine" in cat_choice else ("bromfc" if "BromFC" in cat_choice else "futbol")

    # Day
    st.markdown("<div class='sb-label'>Gün</div>", unsafe_allow_html=True)
    day_opts      = [f"{TR_SHORT[i]}  ·  {week_days[i].strftime('%d %b')}" for i in range(7)]
    sel_day_label = st.selectbox("", day_opts, index=today.weekday(), label_visibility="collapsed")
    sel_day       = week_days[day_opts.index(sel_day_label)]

    # ── FUTBOL SEARCH ──────────────────────────────────────────────────────
    if sel_cat == "futbol":
        st.markdown("<div class='sb-label'>Takım / Oyuncu Ara</div>", unsafe_allow_html=True)
        search_q = st.text_input("", placeholder="örn: Galatasaray, Haaland...",
                                 label_visibility="collapsed", key="search_input")
        if st.button("🔍  Ara", use_container_width=True):
            if search_q.strip():
                with st.spinner("Aranıyor..."):
                    st.session_state.search_results = sofa_search(search_q.strip())
                    st.session_state.search_entity  = None
                    st.session_state.search_matches  = []

        # Search results
        if st.session_state.search_results:
            st.markdown("<div class='sb-label'>Sonuçlar</div>", unsafe_allow_html=True)
            for idx, res in enumerate(st.session_state.search_results):
                label = f"{res['label']} · {res['t_name']}" if res["type"] == "player" else res["label"]
                if st.button(label, key=f"sr_{idx}", use_container_width=True):
                    with st.spinner("Maçlar yükleniyor..."):
                        mlist = get_team_next_matches(res["t_id"], week_days[0].isoformat())
                        st.session_state.search_matches  = mlist
                        st.session_state.search_entity   = res
                        st.session_state.search_results  = []

        # Match choices
        if st.session_state.search_matches:
            entity = st.session_state.search_entity or {}
            st.markdown(f"<div class='sb-label'>{entity.get('name','')} — Bu Hafta</div>", unsafe_allow_html=True)
            if not st.session_state.search_matches:
                st.caption("Bu hafta maç bulunamadı.")
            for midx, m in enumerate(st.session_state.search_matches):
                score_txt = f" {m['score']}" if m["score"] else f" {m['time']}"
                icon = "🔴" if m["status"] == "inprogress" else ("✅" if m["status"] == "finished" else "📅")
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

    # ── DIFINE / BROMFC TEXT ──────────────────────────────────────────────
    else:
        st.markdown("<div class='sb-label'>Not / Görev</div>", unsafe_allow_html=True)
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
    <div class='legend-row'><div class='legend-pip' style='background:#22c55e;'></div>
        <span><b style='color:#22c55e;'>Ekip & Futbol</b></span></div>
    <div class='legend-row'><div class='legend-pip' style='background:#fd2453;'></div>
        <span><b style='color:#fd2453;'>Difine Media</b></span></div>
    <div class='legend-row'><div class='legend-pip' style='background:#3B82F6;'></div>
        <span><b style='color:#3B82F6;'>BromFC</b></span></div>
    """, unsafe_allow_html=True)
    st.markdown(f"""
    <div style='margin-top:16px;font-family:var(--mono);font-size:0.53rem;color:#1a202c;'>
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
TR_MONTHS = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",
             7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"}
TR_DAYS_FULL = {0:"Pazartesi",1:"Salı",2:"Çarşamba",3:"Perşembe",4:"Cuma",5:"Cumartesi",6:"Pazar"}

def fmt_date_tr(d):
    return f"{d.day} {TR_MONTHS[d.month]}"

st.markdown(f"""
<div class='masthead-wrap'>
    <div>
        <div class='masthead-title'><b>F41 · TAKVİM</b></div>
        <div class='masthead-sub'>
            {fmt_date_tr(week_days[0])} — {fmt_date_tr(week_days[6])} {week_days[6].year}
        </div>
    </div>
    <div class='masthead-right'>
        <span>{TR_DAYS_FULL[nw.weekday()]}, {fmt_date_tr(nw.date())} {nw.year}</span><br>
        {nw.strftime('%H:%M')}
    </div>
</div>
""", unsafe_allow_html=True)

# ── SUMMARY STRIP ─────────────────────────────────────────────────────────────
live_pill = (f"<div class='summary-pill sp-live'><div class='sp-dot'></div>{live_count} CANLI</div>"
             if live_count > 0 else "")
st.markdown(f"""
<div class='summary-strip'>
    <div class='summary-pill sp-matches'><div class='sp-dot'></div>{total_matches} Maç</div>
    <div class='summary-pill sp-difine'><div class='sp-dot'></div>{total_difine} Difine</div>
    <div class='summary-pill sp-bromfc'><div class='sp-dot'></div>{total_bromfc} BromFC</div>
    {live_pill}
</div>
""", unsafe_allow_html=True)

# ── CALENDAR GRID ─────────────────────────────────────────────────────────────
cols = st.columns(7, gap="small")

for i, day in enumerate(week_days):
    is_today  = (day == today)
    is_past   = (day < today)
    d_str     = day.isoformat()

    day_matches = sorted(auto_matches.get(d_str, []), key=lambda x: x["time"])
    day_entries = st.session_state.entries.get(d_str, [])

    opacity = "0.35" if is_past else ("1" if is_today else "0.82")
    today_cls = "dh-today" if is_today else ""
    today_dot = "<span class='today-pip'></span>" if is_today else ""

    with cols[i]:
        with st.container(border=True):
            st.markdown(f"<div style='opacity:{opacity};transition:opacity .2s;'>", unsafe_allow_html=True)

            # Header
            st.markdown(f"""
            <div class='day-header {today_cls}'>
                <div class='dh-name'>{TR_FULL[i]}{today_dot}</div>
                <div class='dh-date'>{day.strftime('%d %b')}</div>
            </div>
            """, unsafe_allow_html=True)

            # Auto Ekip matches
            for m in day_matches:
                last_names  = [p.split()[-1] for p in m["players"][:3]]
                players_str = " · ".join(last_names)
                if len(m["players"]) > 3:
                    players_str += f" +{len(m['players'])-3}"

                if m["status"] == "inprogress":
                    badge      = "<span class='badge b-live'>● CANLI</span>"
                    score_part = f" <span class='live-score'>{m['score']}</span>" if m["score"] else ""
                elif m["status"] == "finished":
                    badge      = "<span class='badge b-done'>MS</span>"
                    score_part = f" <b>{m['score']}</b>" if m["score"] else ""
                else:
                    badge = ""
                    try:
                        match_dt = datetime.datetime.strptime(f"{d_str} {m['time']}", "%Y-%m-%d %H:%M")
                        diff_min = (match_dt - nw.replace(tzinfo=None)).total_seconds() / 60
                        if 0 < diff_min <= 180:
                            h = int(diff_min // 60)
                            mn = int(diff_min % 60)
                            soon_txt = f"{h}s {mn}dk" if h > 0 else f"{mn}dk"
                            badge = f"<span class='badge b-soon'>{soon_txt} kaldı</span>"
                    except:
                        pass
                    score_part = f" {m['time']}"

                st.markdown(f"""
                <div class='cal-entry e-ekip'>
                    <div class='e-lbl'>⚽ Ekip {badge}</div>
                    <div class='e-txt'>{m['home']} – {m['away']}{score_part}</div>
                    <div class='e-sub'>{players_str}</div>
                </div>
                """, unsafe_allow_html=True)

            # Manual entries
            to_remove = None
            for entry in list(day_entries):
                cat = entry.get("cat", "difine")

                if cat == "manual_match":
                    status = entry.get("status", "notstarted")
                    score  = entry.get("score", "")
                    if status == "inprogress":
                        badge      = "<span class='badge b-live'>● CANLI</span>"
                        score_part = f" <span class='live-score'>{score}</span>" if score else ""
                    elif status == "finished":
                        badge      = "<span class='badge b-done'>MS</span>"
                        score_part = f" <b>{score}</b>" if score else ""
                    else:
                        badge      = ""
                        score_part = f" {entry.get('time','')}"

                    ec1, ec2 = st.columns([5, 1])
                    with ec1:
                        st.markdown(f"""
                        <div class='cal-entry e-manual-match'>
                            <div class='e-lbl'>⚽ Manuel {badge}</div>
                            <div class='e-txt'>{entry['text']}{score_part}</div>
                            <div class='e-sub'>{entry.get('sub','')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with ec2:
                        if st.button("✕", key=f"del_{entry['id']}", help="Sil"):
                            to_remove = entry["id"]
                else:
                    cat_class = f"e-{cat}"
                    cat_label = "Difine Media" if cat == "difine" else "BromFC"
                    ec1, ec2  = st.columns([5, 1])
                    with ec1:
                        st.markdown(f"""
                        <div class='cal-entry {cat_class}'>
                            <div class='e-lbl'>{cat_label}</div>
                            <div class='e-txt'>{entry['text']}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    with ec2:
                        if st.button("✕", key=f"del_{entry['id']}", help="Sil"):
                            to_remove = entry["id"]

            st.markdown("</div>", unsafe_allow_html=True)

            if to_remove:
                st.session_state.entries[d_str] = [
                    e for e in st.session_state.entries.get(d_str, [])
                    if e["id"] != to_remove
                ]
                st.rerun()

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center;padding:28px 0 8px;
    border-top:1px solid rgba(255,255,255,0.04);margin-top:24px;'>
    <span style='font-family:var(--mono);font-size:0.54rem;color:#111827;letter-spacing:0.14em;text-transform:uppercase;'>
        F41DESIGN · TAKVİM · {nw.strftime('%Y')}
    </span>
</div>
""", unsafe_allow_html=True)
