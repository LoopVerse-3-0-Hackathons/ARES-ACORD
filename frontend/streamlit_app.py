"""ARES ACCORD dashboard. Thin client: all logic lives in the FastAPI backend (ARES_API, default http://localhost:8000)."""
import os, time
import requests, streamlit as st

API = os.environ.get("ARES_API", "http://localhost:8000")
st.set_page_config(page_title="ARES ACCORD", page_icon="🪐", layout="wide")


def call(method, path, **kw):
    try:
        r = requests.request(method, API + path, timeout=10, **kw)
        if r.status_code >= 400: st.error(r.json().get("detail", r.text)); return None
        return r
    except requests.RequestException as e:
        st.error(f"Backend not reachable at {API}: {e}"); st.stop()


@st.cache_data
def meta(): return call("GET", "/api/modes").json()


m = meta(); R, K, M = m["R"], m["K"], m["M"]
S = call("GET", "/api/state").json(); log = call("GET", "/api/transcript").json()
nm = lambda k: {"CMD": "Commander", "Validator": "Validator"}.get(k) or M[k][0]

st.title("ARES ACCORD")
L = S["llm"]; st.caption(f"Backend: {API} · Agents: " + (f"LLM-driven ({L['provider']} / {L['model']}), rule fallback on failure" if L["enabled"] else "RULE-BASED FALLBACK (LLM not configured - set ARES_USE_LLM=1 and an API key)") + " · per-message source: llm / rule-fallback / rule")
with st.sidebar:
    with st.expander("🔑 LLM settings", expanded=not S["llm"]["enabled"]):
        LI = call("GET", "/api/llm").json(); pre = LI["presets"]; provs = list(pre)
        pv = st.selectbox("Provider", provs, index=provs.index(LI["provider"]) if LI["provider"] in provs else 0)
        md = st.text_input("Model", LI["model"] if pv == LI["provider"] else pre[pv]["model"], key="md_" + pv)
        bs = st.text_input("Base URL", LI["base"] if pv == LI["provider"] else pre[pv]["base"], key="bs_" + pv)
        ak = st.text_input("API key", type="password", placeholder=("saved " + LI["key_hint"]) if LI["key_set"] else "paste key", help="Held in backend memory only; not written to disk.")
        on = st.checkbox("Use LLM for agents", LI["enabled"] or not LI["key_set"])
        c1, c2 = st.columns(2)
        if c1.button("Save"): call("POST", "/api/llm/config", json=dict(provider=pv, model=md, base=bs, api_key=ak or None, enabled=on)); st.rerun()
        if c2.button("Test"):
            call("POST", "/api/llm/config", json=dict(provider=pv, model=md, base=bs, api_key=ak or None, enabled=on))
            t = call("POST", "/api/llm/test").json(); (st.success(f"Connected: {t['provider']} / {t['model']}") if t["ok"] else st.error(t["error"]))
    st.header("Judge controls")
    pool = [st.number_input(r, 0, 999, S["pool"][i], key=f"p{i}") for i, r in enumerate(R)]
    pol = st.selectbox("Tie-break policy", ["bal", "hab", "rep"], format_func={"bal": "Balanced", "hab": "Protect habitat", "rep": "Protect repair capacity"}.get)
    if st.button("Start crisis", type="primary", use_container_width=True, disabled=S["running"]): call("POST", "/api/start", json=dict(pool=pool, policy=pol)); st.rerun()
    st.subheader("Inject emergency")
    en = st.text_input("Event name", "Solar aftershock")
    dl = [st.number_input(f"Δ {r}", -999, 999, -4 if i == 0 else 0, key=f"d{i}") for i, r in enumerate(R)]
    ov = st.checkbox("Allow Crisis Override (risk 28, 2 sacrifices)", True)
    if st.button("Inject event", use_container_width=True, disabled=S["running"] or S["status"] != "APPROVED"): call("POST", "/api/event", json=dict(name=en, delta=dl, allow_override=ov)); st.rerun()
    if st.button("Reset everything", use_container_width=True): call("POST", "/api/reset"); st.rerun()
    st.subheader("Export")
    st.download_button("Transcript CSV", call("GET", "/api/export/csv").text, "ares_transcript.csv", "text/csv", use_container_width=True)
    st.download_button("Plan + log JSON", call("GET", "/api/export/json").text, "ares_plan.json", "application/json", use_container_width=True)

p = S["plan"]
st.markdown(f"**Status:** `{S['status']}` · **Scenario:** {S['scen']} · **Round:** {S['round']} · **Plan:** {('v%d %s' % (p['ver'], p['status'])) if p else 'none'} · **Risk limit:** {S['lim']} · **Max sacrifices:** {S['max_sac']}")
tabs = st.tabs(["Mission Control", "Council Transcript", "Mode Board", "Validation"])
with tabs[0]:
    t = [sum(M[k][1][p["sel"][k]][1][i] for k in K) for i in range(5)] if p else [0] * 5
    st.table([{"Resource": R[i], "Pool": S["pool"][i], "Used": t[i], "Reserve": S["pool"][i] - t[i]} for i in range(5)])
    if p: st.metric("Total risk", sum(M[k][1][p["sel"][k]][2] for k in K))
    if S["events"]: st.caption("Events: " + " → ".join(f"{e['name']} {e['delta']}" for e in S["events"]))
with tabs[1]:
    box = st.container(height=520)
    for x in log:
        with box.chat_message("assistant" if x["frm"] in ("CMD", "Validator") else "user"):
            st.markdown(f"**{nm(x['frm'])}** · `{x['type']}` · {x['scenario']} · R{x['round']} · v{x['plan_version']} · _{x['source']}_  \n{x['text']}")
with tabs[2]:
    for c, k in zip(st.columns(4), K):
        with c:
            st.subheader(M[k][0]); st.caption(S["agents"][k]["goal"])
            if p:
                i = p["sel"][k]; pk = M[k][1][i]
                st.markdown(f"**{pk[0]}** · risk {pk[2]}  \n" + " ".join(f"{R[j][0]}{v}" for j, v in enumerate(pk[1])))
                for x in p["commits"]:
                    if x["ben"] == k: st.caption(("✔ " if x["ok"] else "○ ") + f"{nm(x['owner'])}: {x['text']}")
                if k in p["votes"]: st.markdown(f"Vote: **{p['votes'][k]['v']}**")
            st.caption(f"Sacrifice refusals: {S['agents'][k]['refusals']}")
with tabs[3]:
    for x in S["vr"]: st.markdown(f"{'🟢 PASS' if x['ok'] else '🔴 FAIL'} **{x['n']}** — {x['r']}")
    if not S["vr"]: st.caption("No validation yet.")
if S["running"]: time.sleep(1); st.rerun()
