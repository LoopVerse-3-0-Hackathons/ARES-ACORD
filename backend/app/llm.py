"""LLM client. Configure from the dashboard (LLM settings), from .env, or from environment variables.
Providers: anthropic, or any OpenAI-compatible API (openai, groq, openrouter, ollama). ask_json() returns None on any failure -> rule fallback."""
import json, os, re

PRESETS = {"anthropic": dict(kind="anthropic", base="https://api.anthropic.com", model="claude-sonnet-5-5"),
           "openai": dict(kind="openai", base="https://api.openai.com/v1", model="gpt-4o-mini"),
           "groq": dict(kind="openai", base="https://api.groq.com/openai/v1", model="llama-3.3-70b-versatile"),
           "openrouter": dict(kind="openai", base="https://openrouter.ai/api/v1", model="anthropic/claude-sonnet-4.5"),
           "ollama": dict(kind="openai", base="http://localhost:11434/v1", model="llama3.1")}
RT = {}  # runtime settings from the dashboard; held in server memory only, never written to disk


def _load_env():
    for d in (os.getcwd(), os.path.dirname(os.getcwd()), os.path.dirname(os.path.dirname(os.getcwd()))):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            for line in open(p, encoding="utf-8"):
                line = line.split("#")[0].strip()
                if "=" in line:
                    k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"\''))
            return


_load_env()


def cfg():
    prov = RT.get("provider") or os.environ.get("ARES_LLM_PROVIDER") or "anthropic"
    if prov not in PRESETS: prov = "openai"
    pre = PRESETS[prov]
    key = RT.get("api_key") or os.environ.get("ARES_LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
    on = RT["enabled"] if "enabled" in RT else os.environ.get("ARES_USE_LLM") != "0"
    return dict(provider=prov, kind=pre["kind"], model=RT.get("model") or os.environ.get("ARES_LLM_MODEL") or pre["model"],
                base=(RT.get("base") or os.environ.get("ARES_LLM_BASE_URL") or pre["base"]).rstrip("/"), key=key, on=on,
                timeout=float(os.environ.get("ARES_LLM_TIMEOUT", "20")))


def enabled():
    c = cfg(); return c["on"] and (bool(c["key"]) or c["provider"] == "ollama")


def info():
    c = cfg(); return dict(enabled=enabled(), provider=c["provider"], model=c["model"], base=c["base"], key_set=bool(c["key"]), key_hint=("..." + c["key"][-4:]) if c["key"] else "")


def set_config(provider=None, model=None, api_key=None, base=None, enabled=None):
    for k, v in dict(provider=provider, model=model, api_key=api_key, base=base).items():
        if v: RT[k] = v.strip()
    if enabled is not None: RT["enabled"] = bool(enabled)
    return info()


def _call(system, user, max_tokens=400):
    import httpx
    c = cfg(); h = {}
    if c["kind"] == "anthropic":
        r = httpx.post(c["base"] + "/v1/messages", timeout=c["timeout"], headers={"x-api-key": c["key"], "anthropic-version": "2023-06-01"},
                       json=dict(model=c["model"], max_tokens=max_tokens, system=system, messages=[dict(role="user", content=user)]))
        r.raise_for_status(); return "".join(b.get("text", "") for b in r.json()["content"])
    if c["key"]: h["Authorization"] = "Bearer " + c["key"]
    r = httpx.post(c["base"] + "/chat/completions", timeout=c["timeout"], headers=h,
                   json=dict(model=c["model"], max_tokens=max_tokens, messages=[dict(role="system", content=system), dict(role="user", content=user)]))
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"]


def test():
    """Real round-trip to the configured model; reports the error text (key redacted) if it fails."""
    c = cfg()
    if not (c["key"] or c["provider"] == "ollama"): return dict(ok=False, error="No API key set.")
    try:
        txt = _call("Reply with exactly this JSON and nothing else: {\"ok\": true}", "ping", 30)
        return dict(ok=True, reply=txt.strip()[:80], provider=c["provider"], model=c["model"])
    except Exception as e:
        return dict(ok=False, error=str(e).replace(c["key"], "***")[:300] if c["key"] else str(e)[:300])


def ask_json(system, user, tries=2):
    if not enabled(): return None
    for _ in range(tries):
        try:
            m = re.search(r"\{.*\}", _call(system, user), re.S)
            return json.loads(m.group(0))
        except Exception:
            continue
    return None
