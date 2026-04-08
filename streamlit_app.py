import streamlit as st
from curl_cffi import requests as cfreq
import datetime, uuid, base64, json, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="F41 · TAKVİM", layout="wide",
                   page_icon="📅", initial_sidebar_state="expanded")
st_autorefresh(interval=60_000, key="cal_refresh")

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

def get_week_days():
    t = datetime.date.today()
    m = t - datetime.timedelta(days=t.weekday())
    return [m + datetime.timedelta(days=i) for i in range(7)]

def get_week_id(): return get_week_days()[0].isoformat()
def now_tr():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
def fmt_tr(d): return f"{d.day} {TR_MONTHS[d.month]}"

def load_entries():
    try:
        if os.path.exists(ENTRIES_FILE):
            with open(ENTRIES_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("entries", {}), data.get("week_id", "")
    except: pass
    return {}, ""

def save_entries(entries):
    try:
        with open(ENTRIES_FILE, "w", encoding="utf-8") as f:
            json.dump({"week_id": get_week_id(), "entries": entries},
                      f, ensure_ascii=False, indent=2)
    except: pass

if "initialized" not in st.session_state:
    se, sw = load_entries()
    cw = get_week_id()
    st.session_state.update({
        "entries": se, "week_id": sw,
        "show_reset": (sw != "" and sw != cw),
        "search_results": [], "search_matches": [],
        "search_entity": None,
        "photos": {}, "photos_loaded": False,
        "initialized": True,
    })

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_photo(p_id):
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
    def one(t): return t["isim"], _fetch_photo(t["p_id"])
    with ThreadPoolExecutor(max_workers=10) as exe:
        for f in as_completed([exe.submit(one, t) for t in TAKIP]):
            try:
                n, p = f.result()
                st.session_state.photos[n] = p
            except: pass
    st.session_state.photos_loaded = True

preload_photos()

def chips_html(names):
    out = ""
    for n in names[:4]:
        src = st.session_state.photos.get(n, "")
        if src:
            out += f"<img class='pch' src='{src}' title='{n}'>"
        else:
            ini = "".join(x[0] for x in n.split()[:2])
            out += f"<div class='pch pfb' title='{n}'>{ini}</div>"
    if len(names) > 4:
        out += f"<div class='pch pfb'>+{len(names)-4}</div>"
    return f"<div class='pchips'>{out}</div>" if names else ""

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
                        eid = ev["id"]
                        st_ = ev.get("status",{}).get("type","notstarted")
                        sh  = ev.get("homeScore",{}).get("current","")
                        sa  = ev.get("awayScore",{}).get("current","")
                        sc  = f"{sh}–{sa}" if st_!="notstarted" and sh!="" else ""
                        if eid not in by_ev:
                            by_ev[eid] = {"date":d.isoformat(),
                                "home":ev.get("homeTeam",{}).get("shortName","?"),
                                "away":ev.get("awayTeam",{}).get("shortName","?"),
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
            e = item.get("entity",{})
            t = item.get("type","")
            s = (e.get("sport") or {}).get("slug","")
            if t=="player" and s=="football":
                team = e.get("team",{})
                res.append({"type":"player","label":f"👤 {e.get('name','')}",
                    "name":e.get("name",""),
                    "t_id":str(team.get("id","")),
                    "t_name":team.get("shortName",team.get("name",""))})
            elif t=="team" and s=="football":
                res.append({"type":"team","label":f"🏟 {e.get('name','')}",
                    "name":e.get("name",""),
                    "t_id":str(e.get("id","")),
                    "t_name":e.get("shortName",e.get("name",""))})
        return res[:8]
    except: return []

@st.cache_data(ttl=120, show_spinner=False)
def team_week_matches(t_id, week_start):
    ws = datetime.date.fromisoformat(week_start)
    we = ws + datetime.timedelta(days=6)
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
                        "event_id":ev["id"]}
        except: pass
    return sorted(seen.values(), key=lambda x: x["date"])

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap');

:root {
    --bg:#07070e; --sf:#0c0c15; --s2:#10101a;
    --br:rgba(255,255,255,0.06); --br2:rgba(255,255,255,0.10);
    --tx:#b4c2d6; --bright:#ebf0f8; --mu:#3c4a5e; --su:#5e7080;
    --green:#22c55e; --red:#fd2453; --blue:#3b82f6; --amber:#f59e0b;
    --body:'Inter',system-ui,sans-serif; --mono:'JetBrains Mono',monospace;
}

/* ── BASE ── */
html,body,.stApp { background:var(--bg)!important; color:var(--tx); font-family:var(--body); }
.block-container  { padding:1rem 1.2rem 3rem!important; max-width:1800px!important; }

/* ── SIDEBAR ── */
[data-testid="stSidebar"] {
    background:var(--sf)!important;
    border-right:1px solid var(--br)!important;
}
[data-testid="stSidebarContent"] { padding:1.2rem 0.9rem; }

/* ── MASTHEAD ── */
.mhw {
    display:flex; align-items:center; justify-content:space-between;
    padding:14px 0 12px;
    border-bottom:1px solid var(--br);
    margin-bottom:10px;
}
.mht { font-family:var(--mono); font-size:0.6rem; font-weight:700;
    letter-spacing:0.22em; text-transform:uppercase; color:var(--su); }
.mht b { color:var(--bright); font-size:1.0rem; letter-spacing:0.08em; }
.mhs { font-family:var(--mono); font-size:0.56rem; color:var(--mu); margin-top:2px; }
.mhr { font-family:var(--mono); font-size:0.55rem; color:var(--mu);
    text-align:right; line-height:1.9; }
.mhr span { color:var(--su); }

/* ── SUMMARY PILLS ── */
.sstrip { display:flex; gap:5px; padding:6px 0 12px; flex-wrap:wrap; }
.sp {
    display:inline-flex; align-items:center; gap:5px;
    padding:4px 10px; border-radius:100px; border:1px solid;
    font-family:var(--mono); font-size:0.58rem; font-weight:700;
    letter-spacing:0.05em; white-space:nowrap;
}
.sm { color:#22c55e; border-color:rgba(34,197,94,.2);  background:rgba(34,197,94,.06); }
.sd { color:#fd2453; border-color:rgba(253,36,83,.2);  background:rgba(253,36,83,.06); }
.sb { color:#3b82f6; border-color:rgba(59,130,246,.2); background:rgba(59,130,246,.06); }
.sl { color:#fd2453; border-color:rgba(253,36,83,.35); background:rgba(253,36,83,.08);
    animation:pp 2s ease-in-out infinite; }
@keyframes pp {
    0%,100% { box-shadow:0 0 0 0 rgba(253,36,83,.25); }
    50%      { box-shadow:0 0 0 5px rgba(253,36,83,0); }
}
.sdot { width:5px; height:5px; border-radius:50%; background:currentColor; flex-shrink:0; }

/* ── DAY HEADER ── */
.dh { padding:8px 10px; border-bottom:1px solid var(--br); margin-bottom:6px; }
.dhn { font-weight:700; font-size:0.67rem; color:var(--su); }
.dhd { font-family:var(--mono); font-size:0.53rem; color:var(--mu); margin-top:1px; }
.dht .dhn { color:var(--blue); }
.dht .dhd { color:rgba(59,130,246,.42); }
.tpip {
    display:inline-block; width:4px; height:4px; border-radius:50%;
    background:var(--blue); margin-left:4px; vertical-align:middle;
    animation:pip 2s ease-in-out infinite;
}
@keyframes pip { 0%,100%{opacity:1;} 50%{opacity:0.15;} }

/* ── AUTO MATCH CARD ── */
.acard {
    padding:6px 8px 7px;
    border-radius:6px;
    margin-bottom:4px;
    border-left:2.5px solid #22c55e;
    background:rgba(34,197,94,.065);
}
.albl {
    font-family:var(--mono); font-size:0.46rem; letter-spacing:0.09em;
    text-transform:uppercase; margin-bottom:2px; opacity:0.42;
    display:flex; align-items:center; gap:4px; flex-wrap:nowrap;
}
.atxt { font-weight:600; color:var(--bright); font-size:0.65rem; line-height:1.35; }

/* ── BADGES — critical: white-space nowrap ── */
.bdg {
    display:inline-flex; align-items:center; gap:2px;
    padding:1px 5px; border-radius:3px;
    font-family:var(--mono); font-size:0.46rem; font-weight:700;
    letter-spacing:0.04em; vertical-align:middle;
    white-space:nowrap; flex-shrink:0;
}
.bl {
    color:#fd2453; background:rgba(253,36,83,.11);
    border:1px solid rgba(253,36,83,.28);
    animation:blink 1.4s ease-in-out infinite;
}
@keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0.3;} }
.bd { color:#22c55e; background:rgba(34,197,94,.09); border:1px solid rgba(34,197,94,.2); }
.bs { color:#f59e0b; background:rgba(245,158,11,.09); border:1px solid rgba(245,158,11,.2); }
.lsc { font-family:var(--mono); font-weight:700; color:var(--bright); font-size:0.66rem; }

/* ── PLAYER CHIPS ── */
.pchips { display:flex; align-items:center; margin-top:4px; }
.pch {
    width:19px; height:19px; border-radius:50%; object-fit:cover;
    border:1.5px solid rgba(34,197,94,.28); margin-right:-4px;
    background:var(--s2); flex-shrink:0; transition:transform .12s;
}
.pch:hover { transform:scale(1.2); z-index:2; }
.pfb {
    display:inline-flex!important; align-items:center; justify-content:center;
    font-family:var(--mono); font-size:0.4rem; font-weight:700;
    color:var(--su); border:1.5px solid var(--br2);
}

/* ── MANUAL ENTRY CARD ── */
.mcard {
    display:flex; align-items:stretch;
    border-radius:6px; margin-bottom:4px;
    overflow:hidden; border:1px solid var(--br2);
    transition:border-color .12s;
}
.mcard:hover { border-color:rgba(255,255,255,.16); }

.mac { width:3px; flex-shrink:0; }
.mac-difine      { background:#fd2453; }
.mac-bromfc      { background:#3b82f6; }
.mac-manual_match{ background:#22c55e; }

.mhandle {
    width:18px; flex-shrink:0;
    display:flex; align-items:center; justify-content:center;
    cursor:ns-resize; opacity:0.18; transition:opacity .12s;
    font-size:0.62rem; color:var(--su);
    letter-spacing:-1px; user-select:none;
    background:rgba(255,255,255,.012);
}
.mcard:hover .mhandle { opacity:0.45; }

.mbody { flex:1; padding:5px 7px; min-width:0; }
.mcat {
    font-family:var(--mono); font-size:0.45rem; letter-spacing:0.09em;
    text-transform:uppercase; opacity:0.4; margin-bottom:1px;
}
.mcat-difine      { color:#fd2453; }
.mcat-bromfc      { color:#3b82f6; }
.mcat-manual_match{ color:#22c55e; }
.mtxt {
    font-weight:600; color:var(--bright); font-size:0.65rem;
    line-height:1.35; word-break:break-word;
}
.msub { color:var(--mu); font-size:0.55rem; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

/* ── MOVE / DELETE BUTTON COLUMN ── */
.mbtns-col {
    display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    padding:3px 4px; gap:2px; flex-shrink:0;
}

/* Override Streamlit buttons inside .mbtns-col */
.mbtns-col div[data-testid="stButton"] > button {
    width:16px!important;
    height:16px!important;
    min-height:0!important;
    min-width:0!important;
    padding:0!important;
    margin:0!important;
    font-size:0.5rem!important;
    line-height:1!important;
    border-radius:3px!important;
    background:transparent!important;
    border:1px solid var(--br2)!important;
    color:var(--mu)!important;
    display:flex!important;
    align-items:center!important;
    justify-content:center!important;
}
.mbtns-col div[data-testid="stButton"] > button:hover {
    background:rgba(255,255,255,.08)!important;
    color:var(--bright)!important;
    border-color:rgba(255,255,255,.18)!important;
}

/* ── SIDEBAR STYLES ── */
.sbt { font-family:var(--mono); font-size:0.52rem; letter-spacing:0.16em;
    text-transform:uppercase; color:var(--mu); }
.sbt b { color:var(--bright); font-size:0.74rem; }
.sbl { font-family:var(--mono); font-size:0.53rem; font-weight:700;
    letter-spacing:0.1em; text-transform:uppercase; color:var(--mu);
    margin-bottom:5px; margin-top:10px; }
.legr { display:flex; align-items:center; gap:6px; font-size:0.59rem;
    color:var(--mu); margin-bottom:4px; }
.legp { width:6px; height:6px; border-radius:2px; flex-shrink:0; }

/* Global Streamlit overrides */
div[data-testid="stRadio"] label { font-size:0.68rem!important; }
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background:var(--s2)!important; border-color:var(--br2)!important;
    color:var(--tx)!important; font-size:0.68rem!important;
}
div[data-testid="stSelectbox"] > div > div {
    background:var(--s2)!important; border-color:var(--br2)!important;
    font-size:0.68rem!important;
}
div[data-testid="stButton"] > button {
    font-family:var(--mono)!important;
    font-size:0.6rem!important;
    letter-spacing:0.03em;
}
</style>
""", unsafe_allow_html=True)

# ── RUNTIME DATA ──────────────────────────────────────────────────────────────
week_days    = get_week_days()
today        = datetime.date.today()
auto_matches = fetch_week(week_days[0].isoformat())
nw           = now_tr()
cw           = get_week_id()

# ── RESET BANNER ──────────────────────────────────────────────────────────────
if st.session_state.show_reset:
    st.warning("⚠️ **Yeni hafta başladı.** Difine ve BromFC girişleri temizlensin mi?")
    ca, cb, _ = st.columns([3,3,8])
    if ca.button("✓  Temizle, yeni haftaya geç", type="primary"):
        st.session_state.entries={}; st.session_state.week_id=cw
        st.session_state.show_reset=False; save_entries({}); st.rerun()
    if cb.button("Daha sonra"):
        st.session_state.show_reset=False; st.rerun()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='sbt'><b>F41 · TAKVİM</b></div>"
                "<div style='font-family:var(--mono);font-size:0.49rem;color:#181e2a;"
                "letter-spacing:0.09em;margin-bottom:9px;'>YÖNETİM PANELİ</div>",
                unsafe_allow_html=True)
    st.divider()

    st.markdown("<div class='sbl'>Kategori</div>", unsafe_allow_html=True)
    cat_c = st.radio("", ["🔴  Difine Media","🔵  BromFC","🟢  Futbol (Manuel)"],
                     label_visibility="collapsed", key="cat_radio")
    cat = ("difine" if "Difine" in cat_c
           else "bromfc" if "BromFC" in cat_c else "futbol")

    st.markdown("<div class='sbl'>Gün</div>", unsafe_allow_html=True)
    dopts = [f"{TR_SHORT[i]}  ·  {week_days[i].strftime('%d %b')}" for i in range(7)]
    sdl   = st.selectbox("", dopts, index=today.weekday(), label_visibility="collapsed")
    sday  = week_days[dopts.index(sdl)]

    if cat == "futbol":
        st.markdown("<div class='sbl'>Takım / Oyuncu Ara</div>", unsafe_allow_html=True)
        sq = st.text_input("", placeholder="örn: Galatasaray, Mbappé...",
                           label_visibility="collapsed", key="search_input")
        if st.button("🔍  Ara", use_container_width=True):
            if sq.strip():
                with st.spinner("Aranıyor..."):
                    st.session_state.search_results = sofa_search(sq.strip())
                    st.session_state.search_entity  = None
                    st.session_state.search_matches  = []

        if st.session_state.search_results:
            st.markdown("<div class='sbl'>Sonuçlar</div>", unsafe_allow_html=True)
            for idx, res in enumerate(st.session_state.search_results):
                lbl = (f"{res['label']} · {res['t_name']}"
                       if res["type"]=="player" else res["label"])
                if st.button(lbl, key=f"sr_{idx}", use_container_width=True):
                    with st.spinner("Maçlar yükleniyor..."):
                        ml = team_week_matches(res["t_id"], week_days[0].isoformat())
                        st.session_state.search_matches = ml
                        st.session_state.search_entity  = res
                        st.session_state.search_results = []

        if st.session_state.search_matches:
            ent = st.session_state.search_entity or {}
            st.markdown(f"<div class='sbl'>{ent.get('name','')} — Bu Hafta</div>",
                        unsafe_allow_html=True)
            for midx, m in enumerate(st.session_state.search_matches):
                stxt = f" {m['score']}" if m["score"] else f" {m['time']}"
                icon = "🔴" if m["status"]=="inprogress" else ("✅" if m["status"]=="finished" else "📅")
                if st.button(f"{icon} {m['day'][:3]} · {m['home']} – {m['away']}{stxt}",
                             key=f"madd_{midx}", use_container_width=True, type="primary"):
                    d = m["date"]
                    st.session_state.entries.setdefault(d,[]).append({
                        "cat":"manual_match",
                        "text":f"{m['home']} – {m['away']}",
                        "sub":f"{m['time']} · {ent.get('name','')}",
                        "time":m["time"],"status":m["status"],
                        "score":m.get("score",""),"id":uuid.uuid4().hex[:8]})
                    save_entries(st.session_state.entries)
                    st.session_state.search_matches=[]; st.session_state.search_entity=None
                    st.rerun()
    else:
        st.markdown("<div class='sbl'>Not / Görev</div>", unsafe_allow_html=True)
        etxt = st.text_area("", placeholder="Reel, toplantı, görev...",
                            height=80, label_visibility="collapsed", key="txt_input")
        if st.button("➕  Takvime Ekle", use_container_width=True, type="primary"):
            if etxt.strip():
                d = sday.isoformat()
                st.session_state.entries.setdefault(d,[]).append({
                    "cat":cat,"text":etxt.strip(),"id":uuid.uuid4().hex[:8]})
                save_entries(st.session_state.entries); st.rerun()

    st.divider()
    st.markdown("""
    <div class='legr'><div class='legp' style='background:#22c55e;'></div>
        <span><b style='color:#22c55e;'>Ekip & Futbol</b></span></div>
    <div class='legr'><div class='legp' style='background:#fd2453;'></div>
        <span><b style='color:#fd2453;'>Difine Media</b></span></div>
    <div class='legr'><div class='legp' style='background:#3b82f6;'></div>
        <span><b style='color:#3b82f6;'>BromFC</b></span></div>
    """, unsafe_allow_html=True)
    st.markdown(f"<div style='margin-top:11px;font-family:var(--mono);font-size:0.48rem;"
                f"color:#0d131e;'>{nw.strftime('%H:%M:%S')} · 60sn</div>",
                unsafe_allow_html=True)

# ── SUMMARY ───────────────────────────────────────────────────────────────────
tm = sum(len(v) for v in auto_matches.values())
for v in st.session_state.entries.values():
    tm += sum(1 for e in v if e.get("cat")=="manual_match")
td = sum(sum(1 for e in v if e.get("cat")=="difine")
         for v in st.session_state.entries.values())
tb = sum(sum(1 for e in v if e.get("cat")=="bromfc")
         for v in st.session_state.entries.values())
tl = sum(sum(1 for m in v if m.get("status")=="inprogress")
         for v in auto_matches.values())
for v in st.session_state.entries.values():
    tl += sum(1 for e in v if e.get("cat")=="manual_match" and e.get("status")=="inprogress")

st.markdown(f"""
<div class='mhw'>
    <div>
        <div class='mht'><b>F41 · TAKVİM</b></div>
        <div class='mhs'>{fmt_tr(week_days[0])} — {fmt_tr(week_days[6])} {week_days[6].year}</div>
    </div>
    <div class='mhr'>
        <span>{TR_FULL[nw.weekday()]}, {fmt_tr(nw.date())} {nw.year}</span><br>
        {nw.strftime('%H:%M')}
    </div>
</div>
<div class='sstrip'>
    <div class='sp sm'><div class='sdot'></div>{tm} Maç</div>
    <div class='sp sd'><div class='sdot'></div>{td} Difine</div>
    <div class='sp sb'><div class='sdot'></div>{tb} BromFC</div>
    {"<div class='sp sl'><div class='sdot'></div>"+str(tl)+" CANLI</div>" if tl>0 else ""}
</div>
""", unsafe_allow_html=True)

# ── CALENDAR ──────────────────────────────────────────────────────────────────
CAT_LABELS = {"difine":"Difine Media","bromfc":"BromFC","manual_match":"Futbol"}

cols = st.columns(7, gap="small")

for i, day in enumerate(week_days):
    is_today = (day == today)
    is_past  = (day < today)
    d_str    = day.isoformat()

    day_matches = sorted(auto_matches.get(d_str,[]), key=lambda x: x["time"])
    day_entries = list(st.session_state.entries.get(d_str, []))

    op = "0.28" if is_past else ("1.0" if is_today else "0.82")
    tc = "dht" if is_today else ""
    td_dot = "<span class='tpip'></span>" if is_today else ""

    with cols[i]:
        with st.container(border=True):
            st.markdown(f"<div style='opacity:{op};'>", unsafe_allow_html=True)

            # Day header
            st.markdown(f"""
            <div class='dh {tc}'>
                <div class='dhn'>{TR_FULL[i]}{td_dot}</div>
                <div class='dhd'>{day.strftime('%d %b')}</div>
            </div>""", unsafe_allow_html=True)

            # Auto Ekip matches
            for m in day_matches:
                ch = chips_html(m["players"])

                if m["status"] == "inprogress":
                    bdg = "<span class='bdg bl'>● CANLI</span>"
                    sp  = f" <span class='lsc'>{m['score']}</span>" if m["score"] else ""
                elif m["status"] == "finished":
                    bdg = "<span class='bdg bd'>MS</span>"
                    sp  = f" <b>{m['score']}</b>" if m["score"] else ""
                else:
                    bdg = ""
                    sp  = f" {m['time']}"
                    try:
                        mdt = datetime.datetime.strptime(
                            f"{d_str} {m['time']}", "%Y-%m-%d %H:%M")
                        dm  = (mdt - nw.replace(tzinfo=None)).total_seconds() / 60
                        if 0 < dm <= 180:
                            h  = int(dm // 60)
                            mn = int(dm % 60)
                            soon = f"{h}s{mn}dk" if h > 0 else f"{mn}dk"
                            bdg = f"<span class='bdg bs'>{soon}</span>"
                    except:
                        pass

                st.markdown(f"""
                <div class='acard'>
                    <div class='albl'>⚽ EKİP {bdg}</div>
                    <div class='atxt'>{m['home']} – {m['away']}{sp}</div>
                    {ch}
                </div>""", unsafe_allow_html=True)

            # Manual entries with ↑ ↓ ✕
            action = None

            for j, entry in enumerate(day_entries):
                ec  = entry.get("cat","difine")
                lbl = CAT_LABELS.get(ec, ec)
                n   = len(day_entries)

                # Sub line for manual matches
                if ec == "manual_match":
                    s_  = entry.get("status","notstarted")
                    sc  = entry.get("score","")
                    if s_ == "inprogress":
                        sub_content = f"<span class='bdg bl'>● CANLI</span> <span class='lsc'>{sc}</span>"
                    elif s_ == "finished":
                        sub_content = f"<span class='bdg bd'>MS</span> <b>{sc}</b>"
                    else:
                        sub_content = entry.get("sub","")
                    sub_html = f"<div class='msub'>{sub_content}</div>"
                else:
                    sub_html = ""

                # Card + buttons side by side
                c_card, c_btns = st.columns([10, 1])

                with c_card:
                    st.markdown(f"""
                    <div class='mcard'>
                        <div class='mac mac-{ec}'></div>
                        <div class='mhandle'>∶∶</div>
                        <div class='mbody'>
                            <div class='mcat mcat-{ec}'>{lbl}</div>
                            <div class='mtxt'>{entry['text']}</div>
                            {sub_html}
                        </div>
                    </div>""", unsafe_allow_html=True)

                with c_btns:
                    st.markdown("<div class='mbtns-col'>", unsafe_allow_html=True)
                    if st.button("↑", key=f"u_{entry['id']}", disabled=(j==0)):
                        action = ("up", j)
                    if st.button("↓", key=f"d_{entry['id']}", disabled=(j==n-1)):
                        action = ("down", j)
                    if st.button("✕", key=f"x_{entry['id']}"):
                        action = ("del", j)
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            if action:
                act, j = action
                el = list(st.session_state.entries.get(d_str, []))
                if act == "del":
                    el.pop(j)
                elif act == "up" and j > 0:
                    el[j], el[j-1] = el[j-1], el[j]
                elif act == "down" and j < len(el)-1:
                    el[j], el[j+1] = el[j+1], el[j]
                st.session_state.entries[d_str] = el
                save_entries(st.session_state.entries)
                st.rerun()

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='text-align:center;padding:24px 0 6px;
    border-top:1px solid rgba(255,255,255,0.04);margin-top:20px;'>
    <span style='font-family:var(--mono);font-size:0.48rem;color:#080d16;
        letter-spacing:0.12em;text-transform:uppercase;'>
        F41DESIGN · TAKVİM · {nw.strftime('%Y')}
    </span>
</div>
""", unsafe_allow_html=True)
