import streamlit as st
from curl_cffi import requests as cfreq
from streamlit_sortables import sort_items
import datetime, uuid, base64, json, os
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
TR_FULL   = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
TR_SHORT  = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]
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

ENTRIES_FILE = "f41_entries.json"

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

# ── PERSISTENCE ───────────────────────────────────────────────────────────────
def load_entries():
    try:
        if os.path.exists(ENTRIES_FILE):
            with open(ENTRIES_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("entries", {}), data.get("week_id", "")
    except:
        pass
    return {}, ""

def save_entries(entries):
    try:
        with open(ENTRIES_FILE, "w", encoding="utf-8") as f:
            json.dump({"week_id": get_week_id(), "entries": entries},
                      f, ensure_ascii=False, indent=2)
    except:
        pass

# ── SESSION STATE ─────────────────────────────────────────────────────────────
if "initialized" not in st.session_state:
    saved_entries, saved_week = load_entries()
    current_week = get_week_id()
    st.session_state.entries     = saved_entries
    st.session_state.week_id     = saved_week
    st.session_state.show_reset  = (saved_week != "" and saved_week != current_week)
    st.session_state.search_results = []
    st.session_state.search_matches  = []
    st.session_state.search_entity   = None
    st.session_state.photos          = {}
    st.session_state.photos_loaded   = False
    st.session_state.initialized     = True

current_week = get_week_id()

# ── PLAYER PHOTOS (24h cache, once per session) ───────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_photo(p_id: str) -> str:
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
    if st.session_state.photos_loaded:
        return
    def one(t):
        return t["isim"], _fetch_photo(t["p_id"])
    with ThreadPoolExecutor(max_workers=10) as exe:
        for f in as_completed([exe.submit(one, t) for t in TAKIP]):
            try:
                name, photo = f.result()
                st.session_state.photos[name] = photo
            except:
                pass
    st.session_state.photos_loaded = True

preload_photos()

def player_chips_html(names):
    chips = ""
    for name in names[:4]:
        src = st.session_state.photos.get(name, "")
        if src:
            chips += f"<img class='pchip' src='{src}' title='{name}'>"
        else:
            ini = "".join(p[0] for p in name.split()[:2])
            chips += f"<div class='pchip pfb' title='{name}'>{ini}</div>"
    if len(names) > 4:
        chips += f"<div class='pchip pfb'>+{len(names)-4}</div>"
    return f"<div class='pchips'>{chips}</div>"

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
                    "type": "player", "label": f"👤 {entity.get('name','')}",
                    "name": entity.get("name", ""),
                    "t_id": str(team.get("id", "")),
                    "t_name": team.get("shortName", team.get("name", "")),
                })
            elif t == "team" and sport == "football":
                results.append({
                    "type": "team", "label": f"🏟 {entity.get('name','')}",
                    "name": entity.get("name", ""),
                    "t_id": str(entity.get("id", "")),
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
                        "date": d.isoformat(), "day": TR_FULL[d.weekday()],
                        "home": ev.get("homeTeam", {}).get("shortName", "?"),
                        "away": ev.get("awayTeam", {}).get("shortName", "?"),
                        "time": dt.strftime("%H:%M"), "status": st_,
                        "score": f"{sh}–{sa}" if st_ != "notstarted" and sh != "" else "",
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
    --bg:#08080f; --surface:#0d0d16; --s2:#12121c;
    --border:rgba(255,255,255,0.06); --border2:rgba(255,255,255,0.11);
    --text:#bcc8dc; --bright:#edf2f8; --muted:#424f63; --subtle:#667080;
    --green:#22c55e; --red:#fd2453; --blue:#3B82F6; --amber:#f59e0b;
    --body:'Inter',system-ui,sans-serif; --mono:'JetBrains Mono',monospace;
}
html,body,.stApp{background:var(--bg)!important;color:var(--text);font-family:var(--body);}
.block-container{padding:0 1.4rem 3rem!important;max-width:1800px!important;}
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important;}
[data-testid="stSidebarContent"]{padding:1.4rem 1rem;}

/* ── MASTHEAD ── */
.mhw{display:flex;align-items:center;justify-content:space-between;
    padding:22px 0 15px;border-bottom:1px solid var(--border);margin-bottom:12px;}
.mht{font-family:var(--mono);font-size:0.63rem;font-weight:700;
    letter-spacing:0.25em;text-transform:uppercase;color:var(--subtle);}
.mht b{color:var(--bright);font-size:1.1rem;letter-spacing:0.1em;}
.mhs{font-family:var(--mono);font-size:0.6rem;color:var(--muted);margin-top:3px;}
.mhr{font-family:var(--mono);font-size:0.57rem;color:var(--muted);text-align:right;line-height:1.85;}
.mhr span{color:var(--subtle);}

/* ── SUMMARY ── */
.sstrip{display:flex;gap:5px;padding:8px 0 15px;flex-wrap:wrap;}
.sp{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:100px;
    border:1px solid;font-family:var(--mono);font-size:0.6rem;font-weight:700;
    letter-spacing:0.06em;white-space:nowrap;}
.sp-m{color:#22c55e;border-color:rgba(34,197,94,.22);background:rgba(34,197,94,.07);}
.sp-d{color:#fd2453;border-color:rgba(253,36,83,.22);background:rgba(253,36,83,.07);}
.sp-b{color:#3B82F6;border-color:rgba(59,130,246,.22);background:rgba(59,130,246,.07);}
.sp-l{color:#fd2453;border-color:rgba(253,36,83,.4);background:rgba(253,36,83,.1);
    animation:pp 2s ease-in-out infinite;}
@keyframes pp{0%,100%{box-shadow:0 0 0 0 rgba(253,36,83,.3);}50%{box-shadow:0 0 0 5px rgba(253,36,83,0);}}
.sp-dot{width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0;}

/* ── DAY HEADER ── */
.dh{padding:9px 11px;border-bottom:1px solid var(--border);margin-bottom:7px;}
.dhn{font-weight:700;font-size:0.7rem;color:var(--subtle);}
.dhd{font-family:var(--mono);font-size:0.56rem;color:var(--muted);margin-top:2px;}
.dht .dhn{color:var(--blue);} .dht .dhd{color:rgba(59,130,246,.5);}
.tpip{display:inline-block;width:5px;height:5px;border-radius:50%;
    background:var(--blue);margin-left:5px;vertical-align:middle;
    animation:pip 2s ease-in-out infinite;}
@keyframes pip{0%,100%{opacity:1;}50%{opacity:0.2;}}

/* ── EKIP CARDS ── */
.ce{padding:7px 9px 8px;border-radius:7px;margin-bottom:4px;
    border-left:2.5px solid;font-size:0.66rem;line-height:1.45;}
.elbl{font-family:var(--mono);font-size:0.5rem;letter-spacing:0.1em;
    text-transform:uppercase;margin-bottom:3px;opacity:0.48;
    display:flex;align-items:center;gap:5px;}
.etxt{font-weight:600;color:var(--bright);font-size:0.68rem;}
.esub{color:var(--muted);font-size:0.58rem;margin-top:3px;}
.ee{border-color:#22c55e;background:rgba(34,197,94,.07);}

/* ── PLAYER CHIPS ── */
.pchips{display:flex;align-items:center;margin-top:5px;}
.pchip{width:22px;height:22px;border-radius:50%;object-fit:cover;
    border:1.5px solid rgba(34,197,94,.35);margin-right:-5px;
    background:var(--s2);flex-shrink:0;transition:transform .15s;}
.pchip:hover{transform:scale(1.15);z-index:1;}
.pfb{display:inline-flex;align-items:center;justify-content:center;
    font-family:var(--mono);font-size:0.45rem;font-weight:700;color:var(--subtle);
    border:1.5px solid var(--border2);}

/* ── BADGES ── */
.badge{display:inline-flex;align-items:center;gap:3px;padding:1px 5px;
    border-radius:4px;font-family:var(--mono);font-size:0.49rem;
    font-weight:700;letter-spacing:0.05em;vertical-align:middle;}
.bl{color:#fd2453;background:rgba(253,36,83,.12);border:1px solid rgba(253,36,83,.3);
    animation:blk 1.4s ease-in-out infinite;}
@keyframes blk{0%,100%{opacity:1;}50%{opacity:0.35;}}
.bd{color:#22c55e;background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.22);}
.bs{color:#f59e0b;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.22);}
.lsc{font-family:var(--mono);font-weight:700;color:var(--bright);font-size:0.7rem;}

/* ── SORTABLES OVERRIDE ── */
/* These target the streamlit-sortables iframe content via injection */
.sortable-container{background:transparent!important;padding:0!important;}
[data-testid="stIFrame"]{border:none!important;}

/* Delete buttons in day */
div[data-testid="stButton"]>button{
    font-family:var(--mono)!important;font-size:0.6rem!important;
    letter-spacing:0.04em;
}

/* ── SIDEBAR ── */
.sbt{font-family:var(--mono);font-size:0.56rem;letter-spacing:0.18em;
    text-transform:uppercase;color:var(--muted);}
.sbt b{color:var(--bright);font-size:0.78rem;}
.sbl{font-family:var(--mono);font-size:0.57rem;font-weight:700;
    letter-spacing:0.12em;text-transform:uppercase;color:var(--muted);
    margin-bottom:6px;margin-top:12px;}
.legr{display:flex;align-items:center;gap:7px;font-size:0.61rem;color:var(--muted);margin-bottom:5px;}
.legp{width:7px;height:7px;border-radius:2px;flex-shrink:0;}

div[data-testid="stRadio"] label{font-size:0.7rem!important;}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea{
    background:var(--s2)!important;border-color:var(--border2)!important;
    color:var(--text)!important;font-size:0.7rem!important;}
div[data-testid="stSelectbox"]>div>div{
    background:var(--s2)!important;border-color:var(--border2)!important;
    font-size:0.7rem!important;}
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
        save_entries({})
        st.rerun()
    if cb.button("Daha sonra"):
        st.session_state.show_reset = False
        st.rerun()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class='sbt'><b>F41 · TAKVİM</b></div>
    <div style='font-family:var(--mono);font-size:0.52rem;color:#1e293b;
        letter-spacing:0.1em;margin-bottom:10px;'>YÖNETİM PANELİ</div>
    """, unsafe_allow_html=True)
    st.divider()

    st.markdown("<div class='sbl'>Kategori</div>", unsafe_allow_html=True)
    cat_choice = st.radio("", ["🔴  Difine Media","🔵  BromFC","🟢  Futbol (Manuel)"],
                          label_visibility="collapsed", key="cat_radio")
    sel_cat = ("difine" if "Difine" in cat_choice
               else "bromfc" if "BromFC" in cat_choice else "futbol")

    st.markdown("<div class='sbl'>Gün</div>", unsafe_allow_html=True)
    day_opts = [f"{TR_SHORT[i]}  ·  {week_days[i].strftime('%d %b')}" for i in range(7)]
    sel_day_label = st.selectbox("", day_opts, index=today.weekday(), label_visibility="collapsed")
    sel_day = week_days[day_opts.index(sel_day_label)]

    if sel_cat == "futbol":
        st.markdown("<div class='sbl'>Takım / Oyuncu Ara</div>", unsafe_allow_html=True)
        search_q = st.text_input("", placeholder="örn: Galatasaray, Mbappé...",
                                 label_visibility="collapsed", key="search_input")
        if st.button("🔍  Ara", use_container_width=True):
            if search_q.strip():
                with st.spinner("Aranıyor..."):
                    st.session_state.search_results = sofa_search(search_q.strip())
                    st.session_state.search_entity  = None
                    st.session_state.search_matches  = []

        if st.session_state.search_results:
            st.markdown("<div class='sbl'>Sonuçlar</div>", unsafe_allow_html=True)
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
            st.markdown(f"<div class='sbl'>{entity.get('name','')} — Bu Hafta</div>",
                        unsafe_allow_html=True)
            for midx, m in enumerate(st.session_state.search_matches):
                stxt = f" {m['score']}" if m["score"] else f" {m['time']}"
                icon = "🔴" if m["status"]=="inprogress" else ("✅" if m["status"]=="finished" else "📅")
                if st.button(f"{icon} {m['day'][:3]} · {m['home']} – {m['away']}{stxt}",
                             key=f"madd_{midx}", use_container_width=True, type="primary"):
                    d = m["date"]
                    st.session_state.entries.setdefault(d, []).append({
                        "cat": "manual_match",
                        "text": f"{m['home']} – {m['away']}",
                        "sub": f"{m['time']} · {entity.get('name','')}",
                        "time": m["time"], "status": m["status"],
                        "score": m.get("score",""), "id": uuid.uuid4().hex[:8],
                    })
                    save_entries(st.session_state.entries)
                    st.session_state.search_matches = []
                    st.session_state.search_entity  = None
                    st.rerun()
    else:
        st.markdown("<div class='sbl'>Not / Görev</div>", unsafe_allow_html=True)
        entry_text = st.text_area("", placeholder="Reel, toplantı, görev...",
                                  height=80, label_visibility="collapsed", key="txt_input")
        if st.button("➕  Takvime Ekle", use_container_width=True, type="primary"):
            if entry_text.strip():
                d = sel_day.isoformat()
                st.session_state.entries.setdefault(d, []).append({
                    "cat": sel_cat, "text": entry_text.strip(),
                    "id": uuid.uuid4().hex[:8],
                })
                save_entries(st.session_state.entries)
                st.rerun()

    st.divider()
    st.markdown("""
    <div class='legr'><div class='legp' style='background:#22c55e;'></div>
        <span><b style='color:#22c55e;'>Ekip & Futbol</b></span></div>
    <div class='legr'><div class='legp' style='background:#fd2453;'></div>
        <span><b style='color:#fd2453;'>Difine Media</b></span></div>
    <div class='legr'><div class='legp' style='background:#3B82F6;'></div>
        <span><b style='color:#3B82F6;'>BromFC</b></span></div>
    """, unsafe_allow_html=True)
    st.markdown(f"""<div style='margin-top:14px;font-family:var(--mono);
        font-size:0.51rem;color:#111827;'>{nw.strftime('%H:%M:%S')} · 60sn</div>""",
        unsafe_allow_html=True)

# ── SUMMARY ───────────────────────────────────────────────────────────────────
total_m = sum(len(v) for v in auto_matches.values())
for v in st.session_state.entries.values():
    total_m += sum(1 for e in v if e.get("cat") == "manual_match")
total_d = sum(sum(1 for e in v if e.get("cat")=="difine")
              for v in st.session_state.entries.values())
total_b = sum(sum(1 for e in v if e.get("cat")=="bromfc")
              for v in st.session_state.entries.values())
live_n  = sum(sum(1 for m in v if m.get("status")=="inprogress")
              for v in auto_matches.values())
for v in st.session_state.entries.values():
    live_n += sum(1 for e in v if e.get("cat")=="manual_match" and e.get("status")=="inprogress")

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='mhw'>
    <div>
        <div class='mht'><b>F41 · TAKVİM</b></div>
        <div class='mhs'>{fmt_date_tr(week_days[0])} — {fmt_date_tr(week_days[6])} {week_days[6].year}</div>
    </div>
    <div class='mhr'>
        <span>{TR_FULL[nw.weekday()]}, {fmt_date_tr(nw.date())} {nw.year}</span><br>
        {nw.strftime('%H:%M')}
    </div>
</div>
""", unsafe_allow_html=True)

live_pill = (f"<div class='sp sp-l'><div class='sp-dot'></div>{live_n} CANLI</div>"
             if live_n > 0 else "")
st.markdown(f"""
<div class='sstrip'>
    <div class='sp sp-m'><div class='sp-dot'></div>{total_m} Maç</div>
    <div class='sp sp-d'><div class='sp-dot'></div>{total_d} Difine</div>
    <div class='sp sp-b'><div class='sp-dot'></div>{total_b} BromFC</div>
    {live_pill}
</div>
""", unsafe_allow_html=True)

# ── CALENDAR ──────────────────────────────────────────────────────────────────
# Sort style for dark theme
SORT_STYLE = """
    background: transparent;
    padding: 0;
    gap: 4px;
"""

CAT_EMOJI = {"difine": "🔴", "bromfc": "🔵", "manual_match": "⚽"}
CAT_LABEL = {"difine": "Difine", "bromfc": "BromFC", "manual_match": "Futbol"}

cols = st.columns(7, gap="small")

for i, day in enumerate(week_days):
    is_today = (day == today)
    is_past  = (day < today)
    d_str    = day.isoformat()

    day_matches = sorted(auto_matches.get(d_str, []), key=lambda x: x["time"])
    day_entries = list(st.session_state.entries.get(d_str, []))

    opacity   = "0.32" if is_past else ("1.0" if is_today else "0.8")
    today_cls = "dht" if is_today else ""
    today_dot = "<span class='tpip'></span>" if is_today else ""

    with cols[i]:
        with st.container(border=True):
            st.markdown(f"<div style='opacity:{opacity};transition:opacity .15s;'>",
                        unsafe_allow_html=True)

            # Day header
            st.markdown(f"""
            <div class='dh {today_cls}'>
                <div class='dhn'>{TR_FULL[i]}{today_dot}</div>
                <div class='dhd'>{day.strftime('%d %b')}</div>
            </div>
            """, unsafe_allow_html=True)

            # Auto Ekip matches
            for m in day_matches:
                chips = player_chips_html(m["players"])
                if m["status"] == "inprogress":
                    badge = "<span class='badge bl'>● CANLI</span>"
                    sp    = (f" <span class='lsc'>{m['score']}</span>"
                             if m["score"] else "")
                elif m["status"] == "finished":
                    badge = "<span class='badge bd'>MS</span>"
                    sp    = f" <b>{m['score']}</b>" if m["score"] else ""
                else:
                    badge = ""
                    sp    = f" {m['time']}"
                    try:
                        mdt = datetime.datetime.strptime(f"{d_str} {m['time']}", "%Y-%m-%d %H:%M")
                        dm  = (mdt - nw.replace(tzinfo=None)).total_seconds() / 60
                        if 0 < dm <= 180:
                            h = int(dm//60); mn = int(dm%60)
                            t = f"{h}s {mn}dk" if h > 0 else f"{mn}dk"
                            badge = f"<span class='badge bs'>{t} kaldı</span>"
                    except:
                        pass

                st.markdown(f"""
                <div class='ce ee'>
                    <div class='elbl'>⚽ Ekip {badge}</div>
                    <div class='etxt'>{m['home']} – {m['away']}{sp}</div>
                    {chips}
                </div>
                """, unsafe_allow_html=True)

            # ── Manual entries: sortable drag-and-drop ───────────────────────
            if day_entries:
                # Build label strings with encoded IDs (delimiter unlikely to appear in text)
                labels = []
                for e in day_entries:
                    emoji = CAT_EMOJI.get(e["cat"], "·")
                    lbl   = CAT_LABEL.get(e["cat"], "")
                    text  = e["text"]
                    short = text[:24] + ("…" if len(text) > 24 else "")
                    # Encode ID after the separator ‖ (double vertical bar)
                    labels.append(f"{emoji} {lbl} · {short}‖{e['id']}")

                sorted_labels = sort_items(
                    labels,
                    direction="vertical",
                    key=f"sort_{d_str}",
                    custom_style=SORT_STYLE,
                )

                # Detect order change
                sorted_ids   = [l.split("‖")[-1] for l in sorted_labels]
                current_ids  = [e["id"] for e in day_entries]

                if sorted_ids != current_ids:
                    id_map = {e["id"]: e for e in day_entries}
                    new_order = [id_map[eid] for eid in sorted_ids if eid in id_map]
                    st.session_state.entries[d_str] = new_order
                    save_entries(st.session_state.entries)
                    st.rerun()

                # Delete buttons (small, one per entry in current order)
                to_remove = None
                for e in day_entries:
                    emoji = CAT_EMOJI.get(e["cat"], "·")
                    short = e["text"][:16] + "…" if len(e["text"]) > 16 else e["text"]
                    if st.button(f"✕ {emoji} {short}",
                                 key=f"del_{e['id']}", use_container_width=True):
                        to_remove = e["id"]

                if to_remove:
                    st.session_state.entries[d_str] = [
                        e for e in day_entries if e["id"] != to_remove
                    ]
                    save_entries(st.session_state.entries)
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center;padding:28px 0 8px;
    border-top:1px solid rgba(255,255,255,0.04);margin-top:22px;'>
    <span style='font-family:var(--mono);font-size:0.52rem;color:#0f172a;
        letter-spacing:0.14em;text-transform:uppercase;'>
        F41DESIGN · TAKVİM · {nw.strftime('%Y')}
    </span>
</div>
""", unsafe_allow_html=True)
