"""FastAPI backend. Run: uvicorn app.main:app --port 8000"""
import csv, io, os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import llm, rules as X
from .engine import Engine
from .store import Store

app = FastAPI(title="ARES ACCORD API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("ARES_CORS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
engine = Engine(Store(os.environ.get("ARES_DB", "ares.db")))


class StartIn(BaseModel):
    pool: List[int] = Field([79, 52, 59, 26, 17], min_length=5, max_length=5)
    policy: str = "bal"  # bal | hab | rep


class EventIn(BaseModel):
    name: str = "Unnamed emergency"
    delta: List[int] = Field(min_length=5, max_length=5)  # change per resource, negative reduces
    allow_override: bool = True


class LLMIn(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base: Optional[str] = None
    enabled: Optional[bool] = None


@app.get("/api/llm")
def llm_info(): return {**llm.info(), "presets": {k: dict(model=v["model"], base=v["base"]) for k, v in llm.PRESETS.items()}}

@app.post("/api/llm/config")
def llm_config(b: LLMIn): return llm.set_config(b.provider, b.model, b.api_key, b.base, b.enabled)  # key kept in server memory only

@app.post("/api/llm/test")
def llm_test(): return llm.test()

@app.get("/api/health")
def health(): return {"ok": True}

@app.get("/api/modes")
def modes(): return dict(R=X.R, K=X.K, M=X.M, GOAL=X.GOAL, LOSS=X.LOSS, RET=X.RET)

@app.get("/api/state")
def state(): return engine.snapshot()

@app.get("/api/transcript")
def transcript(since: int = 0): return engine.store.messages(since)

@app.post("/api/start")
def start(b: StartIn):
    try: engine.start(b.pool, b.policy)
    except RuntimeError as e: raise HTTPException(409, str(e))
    return {"started": True}

@app.post("/api/event")
def event(b: EventIn):
    try: engine.inject(b.name, b.delta, b.allow_override)
    except RuntimeError as e: raise HTTPException(409, str(e))
    return {"started": True}

@app.post("/api/reset")
def reset(): engine.reset(); return {"reset": True}

@app.get("/api/export/json")
def export_json():
    s = engine.snapshot()
    return {"mode": "LLM-driven agents when ARES_USE_LLM=1, otherwise rule-based fallback; every message carries a source label (llm / rule-fallback / rule)", "resources": s["pool"], "events": s["events"], "status": s["status"], "plan": s["plan"], "validation": s["vr"], "transcript": engine.store.messages()}

@app.get("/api/export/csv")
def export_csv():
    b = io.StringIO(); w = csv.DictWriter(b, fieldnames=["id", "scenario", "round", "plan_version", "frm", "type", "text", "source"]); w.writeheader(); w.writerows(engine.store.messages())
    return Response(b.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ares_transcript.csv"})


_web = os.path.join(os.path.dirname(__file__), "..", "..", "web")
if os.path.isdir(_web): app.mount("/", StaticFiles(directory=_web, html=True), name="web")  # dashboard at http://localhost:8000
