import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import rules as X
from app.engine import Engine
from app.store import Store


def eng(): return Engine(Store(":memory:"), delay=0)


def test_restricted_fails_and_baseline_paths_valid():
    assert X.tot(dict(LS=1, MED=1, FOOD=1, ENG=1)) == [83, 51, 60, 30, 18]
    for sel in (dict(LS=2, MED=1, FOOD=1, ENG=1), dict(LS=1, MED=1, FOOD=1, ENG=2)):
        p = dict(sel=sel, ver=1, commits=[dict(c, ok=True) for c in X.make_commits(sel)], votes={})
        assert X.ok_all(X.validate(p, [79, 52, 59, 26, 17], 24, 1))


def test_validator_blocks_missing_returns_and_stale_votes():
    sel = dict(LS=2, MED=1, FOOD=1, ENG=1); pool = [79, 52, 59, 26, 17]
    p = dict(sel=sel, ver=1, commits=X.make_commits(sel), votes={})
    assert not X.ok_all(X.validate(p, pool, 24, 1))
    p["commits"] = [dict(c, ok=True) for c in p["commits"]]; p["votes"] = {k: dict(v="ACCEPT", ver=0) for k in X.K}
    assert not X.ok_all(X.validate(p, pool, 24, 1, True))


def test_baseline_run_and_event():
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True)
    s = e.snapshot(); assert s["status"] == "APPROVED" and s["round"] >= 3
    msgs = e.store.messages(); types = [m["type"] for m in msgs]
    assert "Objection" in types and types.count("Commitment") >= 2 and types.count("Vote-ACCEPT") == 4
    assert sum(1 for m in msgs if "REFUSE" in m["text"]) >= 1
    e.inject("Solar aftershock", [-4, 0, 0, 0, 0], True, sync=True)
    s = e.snapshot(); assert s["status"] == "APPROVED" and s["plan"]["ver"] > 2


def test_infeasible_and_inject_guard():
    e = eng(); e.start([10, 10, 10, 10, 10], "bal", sync=True)
    assert e.snapshot()["status"] == "INFEASIBLE"
    try: e.inject("x", [-1, 0, 0, 0, 0], sync=True); assert False
    except RuntimeError: pass


def test_llm_agents_with_rejection(monkeypatch):
    """Fake LLM: Medical REJECTS the first valid plan, so the Commander must move to the next candidate; all output is validated."""
    from app import llm
    state = dict(rejected=False)
    monkeypatch.setattr(llm, "enabled", lambda: True)
    def fake(system, user, tries=2):
        import json; u = json.loads(user)
        if "Choose one candidate" in u["task"]: return dict(choice=0, message="lowest risk")
        if u["task"].startswith("Request"): return dict(mode=0, message="I need Standard.")
        if u["task"].startswith("The combined"): return dict(mode=1, message="I can restrict.")
        if u["task"].startswith("The Commander asks"): return dict(message="Not without returns.")
        if u["task"].startswith("Council needs"): return dict(accept=True, message="I commit.")
        if u["task"].startswith("Vote") and "Medical" in system and not state["rejected"]: state["rejected"] = True; return dict(vote="REJECT", message="Too risky for patients.")
        return dict(vote="ACCEPT", message="OK")
    monkeypatch.setattr(llm, "ask_json", fake)
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True); s = e.snapshot(); msgs = e.store.messages()
    assert s["status"] == "APPROVED" and any(m["type"] == "Vote-REJECT" for m in msgs) and s["plan"]["ver"] >= 4 and any(m["source"] == "llm" for m in msgs)


def test_bad_llm_output_falls_back(monkeypatch):
    from app import llm
    monkeypatch.setattr(llm, "enabled", lambda: True); monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"mode": 7, "nonsense": 1})
    e = eng(); e.start([79, 52, 59, 26, 17], "bal", sync=True)
    assert e.snapshot()["status"] == "APPROVED" and any(m["source"] == "rule-fallback" for m in e.store.messages())


def test_llm_runtime_config_and_test_without_key(monkeypatch):
    from app import llm
    for k in ("ARES_LLM_API_KEY", "ANTHROPIC_API_KEY"): monkeypatch.delenv(k, raising=False)
    llm.RT.clear(); assert not llm.enabled() and llm.test()["ok"] is False
    llm.set_config("groq", "m", "secret-key-1234"); i = llm.info()
    assert i["enabled"] and i["provider"] == "groq" and i["key_hint"] == "...1234" and "secret" not in str(i)
    llm.RT.clear()
