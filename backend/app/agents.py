"""Five LLM-driven agents. Each has its own goal, state, message history and decides independently.
Every decision is validated; invalid/failed LLM output falls back to the rule decision (message source = 'rule-fallback')."""
import json
from . import llm
from .rules import K, M, GOAL, LOSS, pkg, mode_txt, nm

SYS = ("You are the {name} agent in a Mars colony emergency council. Your goal: {goal}. You negotiate with the other department agents and the Commander over one shared resource pool. "
       "You choose ONE complete operating mode (0=Standard, 1=Restricted, 2=Sacrifice); package numbers are fixed and cannot be edited. Be honest about your department's needs and push back on unfair loss. "
       "Reply with ONE JSON object only, matching reply_format, no other text. Messages must be at most 2 sentences.")


def fb(): return "rule-fallback" if llm.enabled() else "rule"
def _msg(r): return isinstance(r, dict) and isinstance(r.get("message"), str) and r["message"].strip()
def _mode(r): return _msg(r) and isinstance(r.get("mode"), int) and 0 <= r["mode"] <= 2


class Agent:
    def __init__(self, id, cur=0, refusals=0):
        self.id, self.name, self.goal, self.cur, self.refusals, self.history = id, M[id][0], GOAL[id], cur, refusals, []

    def observe(self, m): self.history = (self.history + [f"{nm(m['frm'])} [{m['type']}]: {m['text']}"[:260]])[-10:]

    def _ask(self, task, ctx, fmt):
        modes = [dict(mode=i, name=p[0], resources=dict(zip(["power", "water", "oxygen", "robot", "bandwidth"], p[1])), risk=p[2], consequence=mode_txt(self.id, i)) for i, p in enumerate(M[self.id][1])]
        return llm.ask_json(SYS.format(name=self.name, goal=self.goal), json.dumps(dict(task=task, your_modes=modes, your_current_mode=self.cur, context=ctx, recent_messages=self.history[-8:], reply_format=fmt)))

    def proposal(self, ctx):
        r = self._ask("Request the operating mode you want this round and say what you lose if reduced.", ctx, '{"mode":0,"message":"..."}')
        if _mode(r): self.cur = r["mode"]; return self.cur, r["message"], "llm"
        m = pkg(self.id, self.cur)
        return self.cur, f"Requesting {m[0]} (P{m[1][0]} W{m[1][1]} O{m[1][2]} R{m[1][3]} B{m[1][4]}). {mode_txt(self.id, self.cur)}.", fb()

    def counteroffer(self, ctx):
        r = self._ask("The combined requests may exceed the pool. Revise your mode if you can. You may not volunteer Sacrifice yet (mode 0 or 1 only).", ctx, '{"mode":1,"message":"..."}')
        if _mode(r): self.cur = min(r["mode"], 1); return self.cur, r["message"], "llm"
        if ctx["over"] and self.cur < 1: self.cur = 1; return 1, f"Switching to {pkg(self.id, 1)[0]} (risk 5). {mode_txt(self.id, 1)}.", fb()
        return self.cur, f"Holding {pkg(self.id, self.cur)[0]}; cannot reduce further without serious damage.", fb()

    def refuse_sacrifice(self, ctx):
        self.refusals += 1
        r = self._ask("The Commander asks you to take Sacrifice mode. State your position: you will only accept with two return commitments from different agents.", ctx, '{"message":"..."}')
        if _msg(r): return f"REFUSE Sacrifice: {r['message']}", "llm"
        return f"REFUSE Sacrifice ({pkg(self.id, 2)[0]}): {LOSS[self.id]}. Only with two return commitments from different agents.", fb()

    def commit(self, c, ctx):
        r = self._ask(f"Council needs your return commitment for {nm(c['ben'])}: '{c['text']}'. Accept (true) only if you can really honour it, otherwise explain.", dict(ctx, commitment=c["text"]), '{"accept":true,"message":"..."}')
        if _msg(r) and isinstance(r.get("accept"), bool): return r["accept"], r["message"], "llm"
        return True, f"{nm(c['owner'])} -> {nm(c['ben'])}: {c['text']}. Expires: {c['exp']}.", fb()

    def vote(self, plan, valid, ctx):
        """Validator FAIL or missing returns force REJECT; otherwise the agent decides."""
        returns = sum(1 for c in plan["commits"] if c["ben"] == self.id and c["ok"])
        sound = valid and (plan["sel"][self.id] != 2 or returns >= 2)
        if not sound: return dict(v="REJECT", ver=plan["ver"]), "Validator or returns not satisfied.", "rule"
        r = self._ask(f"Vote on plan v{plan['ver']} (validator PASS). ACCEPT only if you can live with your department's mode in it.", dict(ctx, plan=ctx["plan_summary"]), '{"vote":"ACCEPT","message":"..."}')
        if _msg(r) and r.get("vote") in ("ACCEPT", "REJECT"): return dict(v=r["vote"], ver=plan["ver"]), r["message"], "llm"
        return dict(v="ACCEPT", ver=plan["ver"]), ("Returns recorded; accepting the loss." if plan["sel"][self.id] == 2 else "My mode is protected within limits."), fb()


class Commander:
    """Chooses among validator-approved candidate plans; cannot approve without PASS + four matching ACCEPT votes."""
    id, name, goal = "CMD", "Commander", "Coordinate and approve only validated, fully-voted plans"
    history = []
    def observe(self, m): pass

    def choose(self, cands, ctx):
        r = llm.ask_json(SYS.format(name="Commander", goal=self.goal) + " Pick the best candidate by colony-wide safety and fairness.",
                         json.dumps(dict(task="Choose one candidate plan (all already pass the validator).", candidates=cands, context=ctx, reply_format='{"choice":0,"message":"..."}')))
        if _msg(r) and isinstance(r.get("choice"), int) and 0 <= r["choice"] < len(cands): return r["choice"], r["message"], "llm"
        return 0, "Selecting the lowest-risk valid plan.", fb()

    @staticmethod
    def can_approve(checks): return all(c["ok"] for c in checks)


def build_agents(saved=None):
    saved = saved or {}
    a = {k: Agent(k, **saved.get(k, {})) for k in K}; a["CMD"] = Commander(); return a
