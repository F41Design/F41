import streamlit as st
from curl_cffi import requests as cfreq
import datetime, uuid, base64, json, os, html as html_mod
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="F41 · TAKVİM", layout="wide",
                   page_icon="📅", initial_sidebar_state="expanded")
st_autorefresh(interval=60_000, key="cal_refresh")

st.markdown('<link rel="apple-touch-icon" href="https://emojicdn.elk.sh/📅?style=apple">', unsafe_allow_html=True)

TR_FULL   = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
TR_SHORT  = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]
TR_MONTHS = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",
             7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık"}

TAKIP = [
    {"isim":"Ozan Kabak",       "t_id":"2569",  "p_id":"857740"},
    {"isim":"Hakan Çalhanoğlu", "t_id":"2697",  "p_id":"135700"},
    {"isim":"Kenan Yıldız",     "t_id":"2687",  "p_id":"1149011"},
    {"isim":"Milot Rashica",    "t_id":"3050",  "p_id":"800411"},
    {"isim":"Nadiem Amiri",     "t_id":"2556",  "p_id":"327755"},
    {"isim":"Gedson Fernandes", "t_id":"2323",  "p_id":"862055"},
    {"isim":"Zeki Çelik",       "t_id":"2702",  "p_id":"893008"},
    {"isim":"Çağlar Söyüncü",   "t_id":"3052",  "p_id":"758608"},
    {"isim":"Mert Müldür",      "t_id":"3052",  "p_id":"836683"},
    {"isim":"Kenan Karaman",    "t_id":"2530",  "p_id":"168943"},
    {"isim":"Can Uzun",         "t_id":"2674",  "p_id":"1440948"},
    {"isim":"Cenk Tosun",       "t_id":"6063",  "p_id":"72127"},
]

ENTRIES_FILE = "f41_entries.json"

def safe(s): return html_mod.escape(str(s or ""))

def get_week_days():
    t = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)).date()
    return [t - datetime.timedelta(days=t.weekday()) + datetime.timedelta(days=i) for i in range(7)]

def get_week_id(): return get_week_days()[0].isoformat()
def now_tr(): return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
def fmt_tr(d): return f"{d.day} {TR_MONTHS[d.month]}"

# ── PERSISTENCE ───────────────────────────────────────────────────────────────
def load_data():
    try:
        if os.path.exists(ENTRIES_FILE):
            with open(ENTRIES_FILE, encoding="utf-8") as f:
                return json.load(f)
    except: pass
    return {"week_id": "", "days": {}}

def save_data(days_dict):
    try:
        with open(ENTRIES_FILE, "w", encoding="utf-8") as f:
            json.dump({"week_id": get_week_id(), "days": days_dict},
                      f, ensure_ascii=False, indent=2)
    except: pass

# ── SESSION ───────────────────────────────────────────────────────────────────
if "initialized" not in st.session_state:
    data = load_data()
    cw   = get_week_id()
    st.session_state.days          = data.get("days", {})
    st.session_state.show_reset    = (data.get("week_id","") not in ("", cw))
    st.session_state.search_res    = []
    st.session_state.search_match  = []
    st.session_state.search_ent    = None
    st.session_state.photos        = {}
    st.session_state.photos_loaded = False
    st.session_state.initialized   = True

# ── PHOTOS ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def _photo(p_id):
    try:
        r = cfreq.get(f"https://api.sofascore.app/api/v1/player/{p_id}/image",
                      headers={"Referer":"https://www.sofascore.com/"},
                      impersonate="chrome110", timeout=6)
        if r.status_code == 200:
            return f"data:image/png;base64,{base64.b64encode(r.content).decode()}"
    except: pass
    return ""

def preload_photos():
    if st.session_state.photos_loaded: return
    def one(t): return t["isim"], _photo(t["p_id"])
    with ThreadPoolExecutor(max_workers=10) as exe:
        for f in as_completed([exe.submit(one,t) for t in TAKIP]):
            try:
                n,p = f.result(); st.session_state.photos[n] = p
            except: pass
    st.session_state.photos_loaded = True

preload_photos()

def chips_html(names):
    if not names: return ""
    h = ""
    for n in names[:4]:
        src = st.session_state.photos.get(n,"")
        if src:
            h += f"<img class='pch' src='{src}' title='{safe(n)}'>"
        else:
            ini = "".join(x[0] for x in n.split()[:2])
            h += f"<span class='pch pfb'>{safe(ini)}</span>"
    if len(names) > 4:
        h += f"<span class='pch pfb'>+{len(names)-4}</span>"
    return f"<div class='pchips'>{h}</div>"

# ── MATCH FETCH ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_week(week_start):
    ws = datetime.date.fromisoformat(week_start)
    we = ws + datetime.timedelta(days=6)
    by_ev = {}
    def one(itm):
        evs = []
        for p in ["next","last"]:
            try:
                r = cfreq.get(f"https://api.sofascore.com/api/v1/team/{itm['t_id']}/events/{p}/0",
                              impersonate="chrome110", timeout=8).json()
                evs.extend(r.get("events",[]))
            except: pass
        return itm, evs
    with ThreadPoolExecutor(max_workers=10) as exe:
        for f in as_completed([exe.submit(one,t) for t in TAKIP]):
            try:
                itm, evs = f.result()
                for ev in evs:
                    try:
                        dt = (datetime.datetime.fromtimestamp(ev["startTimestamp"], datetime.timezone.utc)
                              + datetime.timedelta(hours=3))
                        d = dt.date()
                        if not (ws <= d <= we): continue
                        eid  = str(ev["id"])
                        st_  = ev.get("status",{}).get("type","notstarted")
                        sh   = ev.get("homeScore",{}).get("current","")
                        sa   = ev.get("awayScore",{}).get("current","")
                        sc   = f"{sh}–{sa}" if st_!="notstarted" and sh!="" else ""
                        home = ev.get("homeTeam",{}).get("shortName","?")
                        away = ev.get("awayTeam",{}).get("shortName","?")
                        if eid not in by_ev:
                            by_ev[eid] = {"eid":eid,"date":d.isoformat(),
                                "home":home,"away":away,
                                "time":dt.strftime("%H:%M"),
                                "status":st_,"score":sc,"players":[]}
                        else:
                            by_ev[eid]["status"] = st_
                            if sc: by_ev[eid]["score"] = sc
                        if itm["isim"] not in by_ev[eid]["players"]:
                            by_ev[eid]["players"].append(itm["isim"])
                    except: pass
            except: pass
    out = {}
    for ev in by_ev.values():
        out.setdefault(ev["date"],[]).append(ev)
    return out

@st.cache_data(ttl=300, show_spinner=False)
def sofa_search(q):
    try:
        r = cfreq.get(f"https://api.sofascore.com/api/v1/search/all/?q={q}",
                      impersonate="chrome110", timeout=8).json()
        res = []
        for item in r.get("results",[])[:15]:
            e = item.get("entity",{}); t = item.get("type","")
            s = (e.get("sport") or {}).get("slug","")
            if t=="player" and s=="football":
                team = e.get("team",{})
                res.append({"type":"player","label":f"👤 {e.get('name','')}",
                    "name":e.get("name",""),"t_id":str(team.get("id","")),
                    "t_name":team.get("shortName",team.get("name",""))})
            elif t=="team" and s=="football":
                res.append({"type":"team","label":f"🏟 {e.get('name','')}",
                    "name":e.get("name",""),"t_id":str(e.get("id","")),
                    "t_name":e.get("shortName",e.get("name",""))})
        return res[:8]
    except: return []

@st.cache_data(ttl=120, show_spinner=False)
def team_week_matches(t_id, week_start):
    ws = datetime.date.fromisoformat(week_start); we = ws + datetime.timedelta(days=6)
    seen = {}
    for p in ["next","last"]:
        try:
            r = cfreq.get(f"https://api.sofascore.com/api/v1/team/{t_id}/events/{p}/0",
                          impersonate="chrome110", timeout=8).json()
            for ev in r.get("events",[]):
                dt = (datetime.datetime.fromtimestamp(ev["startTimestamp"], datetime.timezone.utc)
                      + datetime.timedelta(hours=3))
                d = dt.date()
                if ws <= d <= we:
                    st_ = ev.get("status",{}).get("type","notstarted")
                    sh  = ev.get("homeScore",{}).get("current","")
                    sa  = ev.get("awayScore",{}).get("current","")
                    seen[ev["id"]] = {"date":d.isoformat(),"day":TR_FULL[d.weekday()],
                        "home":ev.get("homeTeam",{}).get("shortName","?"),
                        "away":ev.get("awayTeam",{}).get("shortName","?"),
                        "time":dt.strftime("%H:%M"),"status":st_,
                        "score":f"{sh}–{sa}" if st_!="notstarted" and sh!="" else "",
                        "eid":str(ev["id"])}
        except: pass
    return sorted(seen.values(), key=lambda x: x["date"])

def sync_day(d_str, api_list):
    stored   = list(st.session_state.days.get(d_str, []))
    api_map  = {m["eid"]: m for m in api_list}
    seen_ids = {item["eid"] for item in stored if item.get("type")=="auto"}
    for item in stored:
        if item.get("type")=="auto" and item.get("eid") in api_map:
            m = api_map[item["eid"]]
            item.update({"status":m["status"],"score":m["score"],"players":m["players"]})
    for m in api_list:
        if m["eid"] not in seen_ids:
            new = {"type":"auto","eid":m["eid"],"home":m["home"],"away":m["away"],
                   "time":m["time"],"status":m["status"],"score":m["score"],"players":m["players"]}
            insert_at = len(stored)
            for idx, item in enumerate(stored):
                if item.get("type")=="auto" and item.get("time","99:99") > m["time"]:
                    insert_at = idx; break
            stored.insert(insert_at, new)
    return stored

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap');

:root {
    --bg:#07070d; --sf:#0b0b14; --s2:#0f0f18;
    --br:rgba(255,255,255,0.07); --br2:rgba(255,255,255,0.12);
    --tx:#b0bfd6; --bright:#e8eef8; --mu:#3a4858; --su:#5a6e82;
    --green:#22c55e; --red:#fd2453; --blue:#3b82f6; --amber:#f59e0b;
    --body:'Inter',system-ui,sans-serif; --mono:'JetBrains Mono',monospace;
}

html,body,.stApp { background:var(--bg)!important; color:var(--tx); font-family:var(--body); }
.block-container { padding:0.8rem 1rem 3rem!important; max-width:1900px!important; }

/* ── SIDEBAR — narrower, minimal ── */
[data-testid="stSidebar"] {
    background:var(--sf)!important;
    border-right:1px solid var(--br)!important;
    min-width:200px!important;
    max-width:220px!important;
}
[data-testid="stSidebarContent"] { padding:1rem 0.75rem; }
section[data-testid="stSidebar"] { width:220px!important; }

/* ── MASTHEAD ── */
.mhw {
    display:flex; align-items:center; justify-content:space-between;
    padding:10px 0 9px; border-bottom:1px solid var(--br); margin-bottom:8px;
}
.mht { font-family:var(--mono); font-size:0.6rem; font-weight:700;
    letter-spacing:0.2em; text-transform:uppercase; color:var(--su); }
.mht b { color:var(--bright); font-size:1rem; letter-spacing:0.07em; }
.mhs { font-family:var(--mono); font-size:0.55rem; color:var(--mu); margin-top:2px; }
.mhr { font-family:var(--mono); font-size:0.55rem; color:var(--mu); text-align:right; line-height:1.85; }
.mhr b { color:var(--su); }

/* ── SUMMARY ── */
.sstrip { display:flex; gap:4px; padding:5px 0 10px; flex-wrap:wrap; }
.sp {
    display:inline-flex; align-items:center; gap:5px; padding:4px 10px;
    border-radius:100px; border:1px solid; font-family:var(--mono);
    font-size:0.59rem; font-weight:700; letter-spacing:0.04em; white-space:nowrap;
}
.sm{color:#22c55e;border-color:rgba(34,197,94,.2);background:rgba(34,197,94,.06);}
.sd{color:#fd2453;border-color:rgba(253,36,83,.2);background:rgba(253,36,83,.06);}
.sb{color:#3b82f6;border-color:rgba(59,130,246,.2);background:rgba(59,130,246,.06);}
.sl{color:#fd2453;border-color:rgba(253,36,83,.35);background:rgba(253,36,83,.08);
    animation:ppulse 2s ease-in-out infinite;}
@keyframes ppulse{0%,100%{box-shadow:0 0 0 0 rgba(253,36,83,.22);}50%{box-shadow:0 0 0 4px rgba(253,36,83,0);}}
.sdot{width:5px;height:5px;border-radius:50%;background:currentColor;flex-shrink:0;}

/* ── DAY HEADER ── */
.dh { padding:7px 9px 6px; border-bottom:1px solid var(--br); margin-bottom:5px; }
.dhn { font-weight:700; font-size:0.7rem; color:var(--su); }
.dhd { font-family:var(--mono); font-size:0.54rem; color:var(--mu); margin-top:1px; }
.dht .dhn { color:var(--blue); }
.dht .dhd { color:rgba(59,130,246,.4); }
.tpip {
    display:inline-block; width:4px; height:4px; border-radius:50%;
    background:var(--blue); margin-left:4px; vertical-align:middle;
    animation:pip 2s ease-in-out infinite;
}
@keyframes pip { 0%,100%{opacity:1;} 50%{opacity:0.15;} }

/* ── ITEM CARD ── */
.icard {
    display:flex; align-items:stretch;
    border-radius:6px; margin-bottom:3px;
    overflow:hidden; border:1px solid var(--br2);
    transition:border-color .12s;
}
.icard:hover { border-color:rgba(255,255,255,.18); }
.iacc { width:3px; flex-shrink:0; }
.iacc-auto          { background:#22c55e; }
.iacc-difine        { background:#fd2453; }
.iacc-bromfc        { background:#3b82f6; }
.iacc-manual_match  { background:#22c55e; }
.ibody { flex:1; padding:6px 8px; min-width:0; background:rgba(255,255,255,.022); }
.icat {
    font-family:var(--mono); font-size:0.46rem; letter-spacing:0.09em;
    text-transform:uppercase; margin-bottom:2px; opacity:0.38;
    display:flex; align-items:center; gap:4px;
}
.icat-auto          { color:#22c55e; }
.icat-difine        { color:#fd2453; }
.icat-bromfc        { color:#3b82f6; }
.icat-manual_match  { color:#22c55e; }
.itxt {
    font-weight:600; color:var(--bright); font-size:0.72rem;
    line-height:1.3; overflow-wrap:break-word; word-break:break-word;
}
.isub { color:var(--mu); font-size:0.55rem; margin-top:2px; }

/* ── BADGES ── */
.bdg {
    display:inline-flex; align-items:center; gap:2px; padding:1px 4px;
    border-radius:3px; font-family:var(--mono); font-size:0.45rem;
    font-weight:700; letter-spacing:0.04em; white-space:nowrap; flex-shrink:0;
}
.bl{color:#fd2453;background:rgba(253,36,83,.11);border:1px solid rgba(253,36,83,.28);
    animation:blink 1.4s ease-in-out infinite;}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:0.3;}}
.bd{color:#22c55e;background:rgba(34,197,94,.09);border:1px solid rgba(34,197,94,.2);}
.bs{color:#f59e0b;background:rgba(245,158,11,.09);border:1px solid rgba(245,158,11,.2);}
.lsc{font-family:var(--mono);font-weight:700;color:var(--bright);font-size:0.7rem;}

/* ── PLAYER CHIPS ── */
.pchips{display:flex;align-items:center;margin-top:4px;}
.pch{width:18px;height:18px;border-radius:50%;object-fit:cover;
    border:1.5px solid rgba(34,197,94,.25);margin-right:-3px;
    background:var(--s2);flex-shrink:0;}
.pfb{display:inline-flex;align-items:center;justify-content:center;
    font-family:var(--mono);font-size:0.38rem;font-weight:700;
    color:var(--su);border:1.5px solid var(--br2);}

/* ── REORDER BUTTONS — stacked in one column, tiny ── */
div[data-testid="stButton"] > button.reorder {
    width:20px!important; height:20px!important;
    min-height:0!important; min-width:0!important;
    padding:0!important; margin:0 0 2px 0!important;
    font-size:0.55rem!important; line-height:1!important;
    border-radius:4px!important;
    background:rgba(255,255,255,.03)!important;
    border:1px solid var(--br2)!important;
    color:var(--mu)!important;
    display:flex!important; align-items:center!important; justify-content:center!important;
}
div[data-testid="stButton"] > button:hover {
    background:rgba(255,255,255,.08)!important;
    color:var(--bright)!important;
}

/* ── SIDEBAR ── */
.sbt { font-family:var(--mono); font-size:0.52rem; letter-spacing:0.15em;
    text-transform:uppercase; color:var(--mu); }
.sbt b { color:var(--bright); font-size:0.75rem; }
.sbl { font-family:var(--mono); font-size:0.53rem; font-weight:700;
    letter-spacing:0.1em; text-transform:uppercase; color:var(--mu);
    margin-bottom:4px; margin-top:10px; }
.legr { display:flex; align-items:center; gap:6px;
    font-size:0.59rem; color:var(--mu); margin-bottom:3px; }
.legp { width:6px; height:6px; border-radius:2px; flex-shrink:0; }

/* global Streamlit overrides */
div[data-testid="stRadio"] label { font-size:0.68rem!important; }
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background:var(--s2)!important; border-color:var(--br2)!important;
    color:var(--tx)!important; font-size:0.68rem!important; }
div[data-testid="stSelectbox"]>div>div {
    background:var(--s2)!important; border-color:var(--br2)!important;
    font-size:0.67rem!important; }

/* ── COLUMN LAYOUT ── */
/* Columns align to top — cards don't stretch to column height */
[data-testid="stHorizontalBlock"] {
    gap: 3px !important;
    align-items: start !important;
}

/* Zero out all element-container padding in calendar columns */
[data-testid="stMain"] [data-testid="column"]
  [data-testid="element-container"] {
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stMain"] [data-testid="column"]
  [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}

/* ✕ delete button — small, square, no extra space */
[data-testid="stMain"] [data-testid="column"]
  div[data-testid="stButton"] > button[kind="secondary"] {
    width: 20px !important;
    height: 20px !important;
    min-height: 0 !important;
    min-width: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    font-size: 0.52rem !important;
    line-height: 1 !important;
    border-radius: 4px !important;
    background: rgba(255,255,255,.03) !important;
    border: 1px solid rgba(255,255,255,.08) !important;
    color: #3e5060 !important;
    font-family: var(--mono) !important;
}
[data-testid="stMain"] [data-testid="column"]
  div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: rgba(253,36,83,.12) !important;
    color: #fd2453 !important;
    border-color: rgba(253,36,83,.3) !important;
}
</style>
""", unsafe_allow_html=True)

# ── RUNTIME ───────────────────────────────────────────────────────────────────
week_days   = get_week_days()
today       = now_tr().date()
api_matches = fetch_week(week_days[0].isoformat())
nw          = now_tr()
cw          = get_week_id()

changed = False
for day in week_days:
    d = day.isoformat()
    merged = sync_day(d, api_matches.get(d,[]))
    if merged != st.session_state.days.get(d):
        st.session_state.days[d] = merged; changed = True
if changed: save_data(st.session_state.days)

# ── RESET BANNER ──────────────────────────────────────────────────────────────
if st.session_state.show_reset:
    st.warning("⚠️ **Yeni hafta başladı.** Manuel girişler temizlensin mi?")
    ca, cb, _ = st.columns([3,3,8])
    if ca.button("✓  Temizle, yeni haftaya geç", type="primary"):
        for d in st.session_state.days:
            st.session_state.days[d] = [x for x in st.session_state.days[d] if x.get("type")=="auto"]
        st.session_state.show_reset = False
        save_data(st.session_state.days); st.rerun()
    if cb.button("Daha sonra"):
        st.session_state.show_reset = False; st.rerun()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='sbt'><b>F41 · TAKVİM</b></div>", unsafe_allow_html=True)
    st.divider()

    st.markdown("<div class='sbl'>Kategori</div>", unsafe_allow_html=True)
    cat_c = st.radio("", ["🔴 Difine","🔵 BromFC","🟢 Futbol"],
                     label_visibility="collapsed", key="cat_radio")
    cat = "difine" if "Difine" in cat_c else "bromfc" if "BromFC" in cat_c else "futbol"

    st.markdown("<div class='sbl'>Gün</div>", unsafe_allow_html=True)
    dopts = [f"{TR_SHORT[i]} · {week_days[i].strftime('%d %b')}" for i in range(7)]
    sdl   = st.selectbox("", dopts, index=today.weekday(), label_visibility="collapsed")
    sday  = week_days[dopts.index(sdl)]

    if cat == "futbol":
        st.markdown("<div class='sbl'>Ara</div>", unsafe_allow_html=True)
        sq = st.text_input("", placeholder="Galatasaray, Mbappé...",
                           label_visibility="collapsed", key="si")
        if st.button("🔍 Ara", use_container_width=True):
            if sq.strip():
                with st.spinner("..."):
                    st.session_state.search_res   = sofa_search(sq.strip())
                    st.session_state.search_ent   = None
                    st.session_state.search_match  = []

        if st.session_state.search_res:
            for idx, res in enumerate(st.session_state.search_res):
                lbl = f"{res['label']} · {res['t_name']}" if res["type"]=="player" else res["label"]
                if st.button(lbl, key=f"sr_{idx}", use_container_width=True):
                    with st.spinner("..."):
                        ml = team_week_matches(res["t_id"], week_days[0].isoformat())
                        st.session_state.search_match = ml
                        st.session_state.search_ent   = res
                        st.session_state.search_res   = []

        if st.session_state.search_match:
            ent = st.session_state.search_ent or {}
            st.caption(f"{ent.get('name','')} — bu hafta")
            for midx, m in enumerate(st.session_state.search_match):
                stxt = f" {m['score']}" if m["score"] else f" {m['time']}"
                icon = "🔴" if m["status"]=="inprogress" else "✅" if m["status"]=="finished" else "📅"
                if st.button(f"{icon} {m['day'][:3]} · {m['home']} – {m['away']}{stxt}",
                             key=f"madd_{midx}", use_container_width=True, type="primary"):
                    d = m["date"]
                    st.session_state.days.setdefault(d,[]).append({
                        "type":"manual_match","id":uuid.uuid4().hex[:8],
                        "cat":"manual_match",
                        "text":f"{m['home']} – {m['away']}",
                        "sub":f"{m['time']} · {ent.get('name','')}",
                        "time":m["time"],"status":m["status"],"score":m.get("score",""),
                    })
                    save_data(st.session_state.days)
                    st.session_state.search_match=[]; st.session_state.search_ent=None
                    st.rerun()
    else:
        st.markdown("<div class='sbl'>Not / Görev</div>", unsafe_allow_html=True)
        etxt = st.text_area("", placeholder="Reel, toplantı, görev...",
                            height=75, label_visibility="collapsed", key="ti")
        if st.button("➕ Takvime Ekle", use_container_width=True, type="primary"):
            if etxt.strip():
                d = sday.isoformat()
                st.session_state.days.setdefault(d,[]).append({
                    "type":"manual","id":uuid.uuid4().hex[:8],
                    "cat":cat,"text":etxt.strip()})
                save_data(st.session_state.days); st.rerun()

    st.divider()
    st.markdown("""
    <div class='legr'><div class='legp' style='background:#22c55e;'></div>Ekip & Futbol</div>
    <div class='legr'><div class='legp' style='background:#fd2453;'></div>Difine Media</div>
    <div class='legr'><div class='legp' style='background:#3b82f6;'></div>BromFC</div>
    """, unsafe_allow_html=True)
    st.markdown(f"<div style='margin-top:10px;font-family:var(--mono);font-size:0.46rem;"
                f"color:#0c1220;'>{nw.strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

# ── SUMMARY ───────────────────────────────────────────────────────────────────
tm = sum(sum(1 for i in v if i.get("type") in ("auto","manual_match"))
         for v in st.session_state.days.values())
td = sum(sum(1 for i in v if i.get("cat")=="difine")
         for v in st.session_state.days.values())
tb = sum(sum(1 for i in v if i.get("cat")=="bromfc")
         for v in st.session_state.days.values())
tl = sum(sum(1 for i in v if i.get("status")=="inprogress")
         for v in st.session_state.days.values())

st.markdown(f"""
<div class='mhw'>
    <div>
        <div class='mht'><b>F41 · TAKVİM</b></div>
        <div class='mhs'>{fmt_tr(week_days[0])} — {fmt_tr(week_days[6])} {week_days[6].year}</div>
    </div>
    <div class='mhr'><b>{TR_FULL[nw.weekday()]}, {fmt_tr(nw.date())}</b><br>{nw.strftime('%H:%M')}</div>
</div>
<div class='sstrip'>
    <div class='sp sm'><div class='sdot'></div>{tm} Maç</div>
    <div class='sp sd'><div class='sdot'></div>{td} Difine</div>
    <div class='sp sb'><div class='sdot'></div>{tb} BromFC</div>
    {"<div class='sp sl'><div class='sdot'></div>"+str(tl)+" CANLI</div>" if tl>0 else ""}
</div>
""", unsafe_allow_html=True)

# ── CALENDAR ──────────────────────────────────────────────────────────────────
CAT_LABEL = {"auto":"EKİP","difine":"DİFİNE","bromfc":"BROMFC","manual_match":"FUTBOL"}
CAT_ICON  = {"auto":"⚽","manual_match":"⚽"}

grid = st.columns(7, gap="small")

for i, day in enumerate(week_days):
    is_today = (day == today)
    is_past  = (day < today)
    d_str    = day.isoformat()
    items    = list(st.session_state.days.get(d_str, []))
    n        = len(items)
    op       = 0.27 if is_past else (1.0 if is_today else 0.82)
    tc       = "dht" if is_today else ""
    dot      = "<span class='tpip'></span>" if is_today else ""

    with grid[i]:
        with st.container(border=True):
            st.markdown(f"""
            <div class='dh {tc}' style='opacity:{op};'>
                <div class='dhn'>{TR_FULL[i]}{dot}</div>
                <div class='dhd'>{day.strftime('%d %b')}</div>
            </div>""", unsafe_allow_html=True)

            action = None

            def sort_key(x):
                c = x.get("cat", x.get("type",""))
                if c == "difine": return 0
                if c == "bromfc": return 1
                return 2

            items_sorted = sorted(items, key=sort_key)

            for j, item in enumerate(items_sorted):
                itype = item.get("type","manual")
                icat  = item.get("cat", itype)
                lbl   = CAT_LABEL.get(icat, icat.upper())
                icon  = CAT_ICON.get(icat, "")
                can_del = (itype != "auto")

                badge = ""; score_html = ""
                if itype in ("auto","manual_match"):
                    st_ = item.get("status","notstarted")
                    sc  = item.get("score","")
                    if st_ == "inprogress":
                        badge      = "<span class='bdg bl'>● CANLI</span>"
                        score_html = f"<span class='lsc'> {safe(sc)}</span>" if sc else ""
                    elif st_ == "finished":
                        badge      = "<span class='bdg bd'>MS</span>"
                        score_html = f" <b>{safe(sc)}</b>" if sc else ""
                    else:
                        t_str = item.get("time","")
                        score_html = f" {safe(t_str)}"
                        if t_str:
                            try:
                                mdt = datetime.datetime.strptime(f"{d_str} {t_str}", "%Y-%m-%d %H:%M")
                                dm  = (mdt - nw.replace(tzinfo=None)).total_seconds() / 60
                                if 0 < dm <= 180:
                                    h=int(dm//60); mn=int(dm%60)
                                    soon = f"{h}s{mn}dk" if h>0 else f"{mn}dk"
                                    badge = f"<span class='bdg bs'>{soon}</span>"
                            except: pass

                ch  = chips_html(item.get("players",[])) if itype=="auto" else ""
                sub = f"<div class='isub'>{safe(item.get('sub',''))}</div>" if icat=="manual_match" else ""

                if itype == "auto":
                    main_txt = f"{safe(item.get('home','?'))} – {safe(item.get('away','?'))}"
                else:
                    main_txt = safe(item.get("text",""))

                card_html = (
                    f"<div class='icard' style='opacity:{op};'>"
                    f"<div class='iacc iacc-{icat}'></div>"
                    f"<div class='ibody'>"
                    f"<div class='icat icat-{icat}'>{icon} {lbl} {badge}</div>"
                    f"<div class='itxt'>{main_txt}{score_html}</div>"
                    f"{sub}{ch}"
                    f"</div></div>"
                )

                if can_del:
                    c_card, c_del = st.columns([12, 1])
                    with c_card:
                        st.markdown(card_html, unsafe_allow_html=True)
                    with c_del:
                        if st.button("✕", key=f"x_{d_str}_{item.get('id',j)}"):
                            action = ("del", item.get("id"))
                else:
                    st.markdown(card_html, unsafe_allow_html=True)

            if action:
                act, eid = action
                el = list(st.session_state.days.get(d_str,[]))
                if act == "del":
                    el = [e for e in el if e.get("id") != eid]
                st.session_state.days[d_str] = el
                save_data(st.session_state.days); st.rerun()

st.markdown(f"""
<div style='text-align:center;padding:20px 0 6px;
    border-top:1px solid rgba(255,255,255,0.04);margin-top:16px;'>
    <span style='font-family:var(--mono);font-size:0.45rem;color:#06080e;
        letter-spacing:0.1em;text-transform:uppercase;'>
        F41DESIGN · TAKVİM · {nw.strftime('%Y')}
    </span>
</div>
""", unsafe_allow_html=True)
