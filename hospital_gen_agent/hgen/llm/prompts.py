"""Prompt helpers for the cognition loop — the hospital analog of run_gpt_prompt_*.

Each helper builds a short inline prompt, routes it through ``claude_backend.llm``,
and parses the reply into the structure the cognitive modules expect. Every helper
supplies a deterministic ``canned`` value so the full pipeline runs offline
(``HGEN_LLM_MODE=canned``). Frequent, cheap calls use ``MODEL_SONNET``; the
low-frequency reflection calls use ``MODEL_OPUS``.

``persona`` is accepted loosely: an object with the attribute, an object exposing
a ``.scratch`` with it, or a plain dict — see ``_field``.
"""
from __future__ import annotations

import re
from typing import Any

from hgen.config import MODEL_OPUS, MODEL_SONNET
from hgen.llm.claude_backend import llm


# --------------------------------------------------------------------------- #
# Small extraction/parsing helpers                                            #
# --------------------------------------------------------------------------- #
def _field(persona: Any, name: str, default: str = "") -> Any:
    """Read ``name`` from a persona-like object (self, ``.scratch``, or dict)."""
    for obj in (persona, getattr(persona, "scratch", None)):
        if obj is None:
            continue
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            val = getattr(obj, name)
            if val is not None:
                return val
    return default


def _lines(raw: str) -> list[str]:
    """Split into clean, de-bulleted, non-empty lines."""
    out = []
    for line in raw.splitlines():
        s = line.strip().lstrip("-*0123456789.) ").strip()
        if s:
            out.append(s)
    return out


def _match_option(raw: str, options: list[str]) -> str:
    """Snap a free-text reply to the closest listed option (default: first)."""
    r = raw.strip().lower()
    if not r:
        return options[0]
    for o in options:
        if o.lower() == r:
            return o
    for o in options:
        if o.lower() in r or r in o.lower():
            return o
    return options[0]


def _first_emoji(s: str) -> str:
    """Extract a single emoji/glyph from a reply."""
    s = s.strip()
    if not s:
        return ""
    if len(s) <= 4:  # already just an emoji token (incl. variation selectors)
        return s
    for ch in s:
        if ord(ch) > 0x2000:  # first symbol/pictograph past basic punctuation
            return ch
    return s[0]


_EMOJI_MAP: list[tuple[tuple[str, ...], str]] = [
    (("vital", "blood pressure", "triage", "stethoscope", "exam"), "\U0001FA7A"),   # 🩺
    (("pregnan", "prenatal", "obstetric", "ob "), "\U0001F930"),                    # 🤰
    (("ultrasound", "fetal", "heart"), "\U0001FAC0"),                               # 🫀
    (("wait",), "⌛"),                                                          # ⌛
    (("walk", "heading", "arriv", "leav", "go to", "going", "enter"), "\U0001F6B6"),# 🚶
    (("discharge", "done", "complete", "finish"), "✅"),                        # ✅
    (("medication", "pharmacy", "med ", "pill", "drug"), "\U0001F48A"),             # 💊
    (("lab", "test", "sample", "draw", "diagnostic"), "\U0001F9EA"),                # 🧪
    (("bed", "rest", "sleep", "lie"), "\U0001F6CF️"),                          # 🛏️
    (("think", "reflect", "consider"), "\U0001F4AD"),                               # 💭
    (("sick", "unwell", "pain", "nause"), "\U0001F912"),                            # 🤒
    (("check", "talk", "chat", "speak", "intake", "history", "consult",
      "reception"), "\U0001F4AC"),                                                  # 💬
]


def _canned_emoji(action_desc: str) -> str:
    t = (action_desc or "").lower()
    for keys, emoji in _EMOJI_MAP:
        if any(k in t for k in keys):
            return emoji
    return "\U0001F4AC"  # 💬


# --------------------------------------------------------------------------- #
# Planning                                                                    #
# --------------------------------------------------------------------------- #
def gen_daily_plan(persona: Any) -> list[str]:
    """Return the ordered care-pathway steps for a persona's hospital visit."""
    name = _field(persona, "name", "the patient")
    currently = _field(persona, "currently", "")
    req = _field(persona, "daily_plan_req", "")
    prompt = (
        f"You are planning the hospital-visit care pathway for {name}.\n"
        f"Currently: {currently}\n"
        f"Goal: {req}\n"
        "List the ordered steps of the visit, one short step per line, no numbering."
    )
    canned = "\n".join(
        [
            "arrive at the hospital and go to Admissions",
            "check in at reception",
            "wait in the waiting room",
            "get triaged (vitals and history)",
            "see the doctor for the consult",
            "receive the care plan",
            "get discharge instructions",
            "go home",
        ]
    )
    raw = llm(prompt, model=MODEL_SONNET, max_tokens=256, canned=canned)
    return _lines(raw)


def _choose(persona: Any, options: Any, kind: str) -> str:
    opts = [str(o) for o in options]
    if not opts:
        return ""
    name = _field(persona, "name", "the agent")
    act = _field(persona, "act_description", "")
    listed = "\n".join(f"- {o}" for o in opts)
    prompt = (
        f"{name} needs the single best {kind} for the current action.\n"
        f"Current action: {act}\n"
        f"Options:\n{listed}\n"
        "Answer with exactly one option from the list."
    )
    raw = llm(prompt, model=MODEL_SONNET, max_tokens=64, canned=opts[0])
    return _match_option(raw, opts)


def gen_action_sector(persona: Any, options: Any) -> str:
    """Pick the department (sector) for the current action."""
    return _choose(persona, options, "sector (hospital department)")


def gen_action_arena(persona: Any, options: Any) -> str:
    """Pick the room (arena) for the current action."""
    return _choose(persona, options, "arena (room)")


def gen_action_game_object(persona: Any, options: Any) -> str:
    """Pick the object the action targets (bed, vitals station, ...)."""
    return _choose(persona, options, "object")


# --------------------------------------------------------------------------- #
# Action annotation                                                           #
# --------------------------------------------------------------------------- #
def gen_pronunciatio(action_desc: str) -> str:
    """Return a single emoji summarizing ``action_desc``."""
    prompt = (
        "Convert this hospital action into a single emoji that best represents it.\n"
        f"Action: {action_desc}\n"
        "Answer with only one emoji."
    )
    canned = _canned_emoji(action_desc)
    raw = llm(prompt, model=MODEL_SONNET, max_tokens=16, canned=canned)
    return _first_emoji(raw) or canned


def gen_event_triple(persona: Any, action_desc: str) -> tuple[str, str, str]:
    """Return the (subject, predicate, object) triple for an action."""
    name = _field(persona, "name", "agent")
    prompt = (
        "Summarize the action as a subject|predicate|object triple.\n"
        f"Subject is '{name}'.\n"
        f"Action: {action_desc}\n"
        "Answer in the form: subject | predicate | object"
    )
    canned = f"{name} | is | {action_desc}"
    raw = llm(prompt, model=MODEL_SONNET, max_tokens=48, canned=canned)
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) >= 3 and all(parts[:3]):
        return (parts[0], parts[1], parts[2])
    return (name, "is", action_desc)


# --------------------------------------------------------------------------- #
# Reactions                                                                   #
# --------------------------------------------------------------------------- #
def decide_to_talk(init: Any, target: Any, context: str = "") -> bool:
    """Decide whether ``init`` should start a conversation with ``target``."""
    a = _field(init, "name", "Agent A")
    b = _field(target, "name", "Agent B")
    prompt = (
        f"{a} and {b} are near each other in the hospital.\n"
        f"Context: {context}\n"
        f"Would {a} start a conversation with {b} right now? Answer yes or no."
    )
    raw = llm(prompt, model=MODEL_SONNET, max_tokens=8, canned="yes")
    return raw.strip().lower().startswith("y")


# --------------------------------------------------------------------------- #
# Reflection (routed to the high-value model)                                 #
# --------------------------------------------------------------------------- #
_PAREN = re.compile(r"\(([^)]*)\)\s*$")


def _parse_insights(raw: str, n: int) -> list[tuple[str, list[int]]]:
    out: list[tuple[str, list[int]]] = []
    for line in _lines(raw):
        thought, idxs = line, []
        m = _PAREN.search(line)
        if m:
            thought = line[: m.start()].strip()
            idxs = [int(t) for t in re.findall(r"\d+", m.group(1)) if 0 <= int(t) < n]
        if thought:
            out.append((thought, idxs))
    return out


def reflect_insights(persona: Any, statements: Any) -> list[tuple[str, list[int]]]:
    """Synthesize higher-level thoughts + supporting evidence indices."""
    stmts = [str(s) for s in statements]
    if not stmts:
        return []
    name = _field(persona, "name", "the agent")
    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(stmts))
    prompt = (
        f"Here are recent memories for {name}:\n{numbered}\n\n"
        "Infer up to 3 high-level insights. Write one insight per line as:\n"
        "insight text (because of 0, 2)\n"
        "where the numbers are the memory indices that support it."
    )
    idxs = ", ".join(str(i) for i in range(min(3, len(stmts))))
    canned = f"{name} is progressing through a hospital visit (because of {idxs})"
    raw = llm(prompt, model=MODEL_OPUS, max_tokens=400, canned=canned)
    return _parse_insights(raw, len(stmts))


def gen_utterance(speaker: Any, listener: Any, context: str,
                  history: Any = None, memories: Any = None) -> tuple[str, bool]:
    """Generate one spoken line for ``speaker`` talking to ``listener``.

    Returns ``(utterance, end)`` where ``end`` signals the speaker is wrapping
    up the conversation. Grounded in the speaker's role/identity and any supplied
    ``memories`` (recallable facts). Canned fallback keeps offline mode working.
    """
    sp = _field(speaker, "name", "Speaker")
    ls = _field(listener, "name", "Listener")
    role = _field(speaker, "learned", "") or _field(speaker, "currently", "")
    convo = "\n".join(f"{who}: {line}" for who, line in (history or []))
    mem = "\n".join(f"- {m}" for m in (memories or []))
    prompt = (
        f"You are {sp}. {role}\n"
        f"You are talking with {ls} in a hospital. Context: {context}\n"
        + (f"Relevant things you know:\n{mem}\n" if mem else "")
        + (f"Conversation so far:\n{convo}\n" if convo else "")
        + f"Say your next line as {sp}, in character, one or two sentences. "
        "If the conversation should end after your line, append ' <END>'."
    )
    canned = f"{sp}: (nods)"
    raw = llm(prompt, model=MODEL_SONNET, max_tokens=220,
              canned=canned).strip()
    end = "<END>" in raw
    raw = raw.replace("<END>", "").strip()
    # Strip a leading "Name:" if the model echoed it.
    if raw.lower().startswith(sp.lower() + ":"):
        raw = raw[len(sp) + 1:].strip()
    return (raw or "(nods)", end)


def memo_on_convo(persona: Any, convo_text: str) -> str:
    """Return the persona's one-sentence takeaway from a conversation."""
    name = _field(persona, "name", "the agent")
    prompt = (
        f"{name} just had this conversation:\n{convo_text}\n\n"
        f"In one sentence, what is {name}'s main takeaway?"
    )
    canned = f"{name} understands the plan after the conversation."
    raw = llm(prompt, model=MODEL_OPUS, max_tokens=200, canned=canned)
    return raw.strip() or canned


if __name__ == "__main__":  # offline demo
    print(gen_pronunciatio("taking vitals"))
    print(gen_daily_plan({"name": "Clarence Reinger", "currently": "here for prenatal intake"}))
    print(gen_event_triple({"name": "Nurse Reyes"}, "taking vitals"))
    print(decide_to_talk({"name": "Clarence"}, {"name": "Nurse Reyes"}))
    print(reflect_insights({"name": "Clarence"}, ["I am pregnant", "I feel anxious", "I saw Dr. Amari"]))
