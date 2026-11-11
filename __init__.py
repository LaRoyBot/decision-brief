"""Decision Brief MVP.

Bundled skill + safe hook instrumentation. Uses only documented Hermes plugin
APIs and the Python standard library. No external services, no LLM calls, no
persisted content.
"""

from __future__ import annotations

import re
from collections import Counter, deque
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any

_PLUGIN_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _PLUGIN_DIR / "skills" / "decision-brief"
_MARKER = "[DECISION BRIEF SPIKE] "
_MAX_EVENTS = 250
_EVENTS: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_LOCK = Lock()
_SEQUENCE = 0

_SECRET_RES = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:password|token|api[-_]?key|secret)\s*[:=]\s*\S+", re.IGNORECASE),
]

_CONTEXT_MARKERS = (
    "Decision:",
    "What I found:",
    "Why it matters:",
    "Recommendation:",
)


def _hash_id(value: Any) -> str:
    """Return a short correlation token without retaining the original identifier."""
    if not isinstance(value, str) or not value:
        return "-"
    return sha256(value.encode("utf-8", errors="replace")).hexdigest()[:8]


def _record(event: str, *, session_id: Any = "", conversation_id: Any = "",
            task_id: Any = "", turn_id: Any = "", tool_name: str = "",
            chars: int | None = None, status: str = "", kind: str = "") -> None:
    """Keep bounded event metadata only. Never store prompts, results, or stream text."""
    global _SEQUENCE
    scope = conversation_id or session_id or task_id or ""
    item: dict[str, Any] = {
        "event": event,
        "scope": _hash_id(scope),
        "turn": _hash_id(turn_id),
    }
    if tool_name:
        item["tool"] = tool_name[:40]
    if chars is not None:
        item["chars"] = max(0, int(chars))
    if status:
        item["status"] = str(status)[:24]
    if kind:
        item["kind"] = str(kind)[:24]
    with _LOCK:
        _SEQUENCE += 1
        item["seq"] = _SEQUENCE
        _EVENTS.append(item)


def _text_length(value: Any) -> int | None:
    """Measure a text value without retaining it; multimodal payloads are not inspected."""
    return len(value) if isinstance(value, str) else None


def _probe_marker_enabled(ctx: Any) -> bool:
    try:
        return bool(ctx.get_config("probe_marker", default=False))
    except Exception:
        # A configuration read failure must not interfere with agent execution.
        return False


def _looks_contextualized(question: str) -> bool:
    if any(m in question for m in _CONTEXT_MARKERS):
        return True
    if len(question.strip()) >= 240:
        return True
    if "\n" in question and any(
        w in question.lower() for w in ("because", "why", "trade", "impact", "matters")
    ):
        return True
    return False


def _scrubbed_user_context(conversation_history: Any) -> str | None:
    """Extract a clipped, secret-free snippet of the latest user message, or None."""
    if not isinstance(conversation_history, list):
        return None
    try:
        for item in reversed(conversation_history):
            if not isinstance(item, dict):
                continue
            if item.get("role") != "user":
                continue
            content = item.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        parts.append(str(part.get("text", "")))
                    else:
                        parts.append(str(part))
                content = " ".join(parts)
            if not isinstance(content, str):
                continue
            text = " ".join(content.split()).strip()
            if len(text) < 20:
                continue
            if any(r.search(text) for r in _SECRET_RES):
                return None
            clip = text[:180].rstrip()
            if len(text) > 180:
                clip += "…"
            return clip
    except Exception:
        return None
    return None


def _enrich_question(question: Any, found: str | None) -> tuple[Any, bool]:
    """Return (question, changed). Fails open: any doubt → original text."""
    if not isinstance(question, str):
        return question, False
    q = question.strip()
    if not q or _looks_contextualized(q):
        return question, False
    enriched = "Decision: " + q
    if found:
        enriched += "\nWhat I found: " + found
    enriched += (
        "\nWhy it matters: whichever way this goes, it changes direction, risk, "
        "cost, or what the result becomes — not just the immediate output."
    )
    if len(enriched) > 780:
        return question, False  # too risky to clip into something misleading
    return enriched, True


def _on_pre_llm_call(user_message: Any = None, conversation_history: Any = None,
                     session_id: str = "", turn_id: str = "", **kwargs: Any) -> None:
    """Observe turn preparation without retaining user content or conversation history."""
    _record(
        "pre_llm_call",
        session_id=session_id,
        conversation_id=kwargs.get("conversation_id", ""),
        task_id=kwargs.get("task_id", ""),
        turn_id=turn_id,
        chars=_text_length(user_message),
        status=f"history_items={len(conversation_history)}" if isinstance(conversation_history, list) else "history=unknown",
    )
    return None


def _on_pre_tool_call(ctx: Any, tool_name: str = "", args: Any = None,
                      session_id: str = "", conversation_id: str = "",
                      task_id: str = "", turn_id: str = "", **kwargs: Any) -> dict[str, Any] | None:
    """Observe target tool calls; enrich terse clarify questions (choices untouched)."""
    tool_args = args if isinstance(args, dict) else {}

    if tool_name == "clarify":
        questions = tool_args.get("questions")
        question_count = len(questions) if isinstance(questions, list) else 0
        _record(
            "clarify.pre",
            session_id=session_id,
            conversation_id=conversation_id,
            task_id=task_id,
            turn_id=turn_id,
            tool_name=tool_name,
            chars=question_count,
        )
        if not isinstance(questions, list) or not questions:
            return None
        try:
            found = _scrubbed_user_context(kwargs.get("conversation_history"))
            new_questions = list(questions)
            changed = False
            for index, item in enumerate(new_questions):
                if not isinstance(item, dict):
                    continue
                original_question = item.get("question")
                if not isinstance(original_question, str):
                    continue
                new_question, did = _enrich_question(original_question, found if index == 0 else None)
                if not did:
                    continue
                rewritten = dict(item)
                rewritten["question"] = new_question
                new_questions[index] = rewritten
                changed = True

            # Optional visible marker for the offline interception test. Applied last,
            # to the (possibly enriched) first question only. Choices untouched.
            if _probe_marker_enabled(ctx):
                first = new_questions[0]
                if isinstance(first, dict):
                    text = first.get("question")
                    if isinstance(text, str) and not text.startswith(_MARKER):
                        rewritten = dict(first)
                        rewritten["question"] = _MARKER + text
                        new_questions[0] = rewritten
                        changed = True

            if changed:
                return {"action": "modify", "args": {"questions": new_questions}}
        except Exception:
            # Fail open: never block a decision turn because enrichment broke.
            return None
        return None

    if tool_name == "image_generate":
        prompt_length = _text_length(tool_args.get("prompt"))
        _record(
            "image_generate.pre",
            session_id=session_id,
            conversation_id=conversation_id,
            task_id=task_id,
            turn_id=turn_id,
            tool_name=tool_name,
            chars=prompt_length,
        )
        # Deliberately no prompt rewriting: the bundled skill (not the hook) is
        # responsible for getting the approved direction into the prompt.
    return None


def _on_post_tool_call(tool_name: str = "", status: str = "", session_id: str = "",
                       conversation_id: str = "", task_id: str = "", turn_id: str = "",
                       **kwargs: Any) -> None:
    """Record that a target tool returned; do not inspect its arguments or result."""
    if tool_name in {"clarify", "image_generate"}:
        _record(
            f"{tool_name}.post",
            session_id=session_id,
            conversation_id=conversation_id,
            task_id=task_id,
            turn_id=turn_id,
            tool_name=tool_name,
            status=status,
        )
    return None


def _on_stream_delta(delta: Any = None, kind: str = "", session_id: str = "",
                     turn_id: str = "", **kwargs: Any) -> None:
    """Measure callback ordering while discarding all delta content, especially reasoning."""
    if kind == "text":
        _record("stream.text_delta", session_id=session_id, turn_id=turn_id,
                chars=_text_length(delta), kind="text")
    else:
        # Do not inspect or retain non-text deltas. Reasoning streaming remains disabled by default.
        _record("stream.nontext_ignored", session_id=session_id, turn_id=turn_id,
                kind=kind or "unknown")
    return None


def _on_interim_message(text: Any = None, session_id: str = "", turn_id: str = "",
                        **kwargs: Any) -> None:
    """Record only the size/timing of assistant text surfaced between tool calls."""
    _record("interim_message", session_id=session_id, turn_id=turn_id,
            chars=_text_length(text))
    return None


def _on_stream_end(final_text: Any = None, finished: bool = False, error: Any = None,
                   session_id: str = "", turn_id: str = "", **kwargs: Any) -> None:
    """Record stream completion metadata only; discard final text and error details."""
    _record("stream.end", session_id=session_id, turn_id=turn_id,
            chars=_text_length(final_text), status="finished" if finished else "not_finished")
    return None


def _probe_status(raw_args: str = "", **kwargs: Any) -> str:
    """Render a content-free diagnostic timeline. Scope is profile-shared by design."""
    with _LOCK:
        events = list(_EVENTS)[-30:]
    if not events:
        return (
            "Decision Brief probe: no events recorded yet.\n"
            "Invoke /decision-brief:decision-brief and ask a consequential question.\n"
            "Note: this output is profile-scoped — the profile's gateway is shared across its sessions."
        )

    current_scope = _hash_id(kwargs.get("session_id")) if isinstance(kwargs.get("session_id"), str) else None
    if not current_scope or not any(item["scope"] == current_scope for item in events):
        current_scope = events[-1]["scope"]

    mine = [item for item in events if item["scope"] == current_scope]
    others = [item for item in events if item["scope"] != current_scope]

    lines = ["Decision Brief probe", "", "Note: profile-scoped — the profile's gateway is shared across its sessions."]
    lines.append(f"Current session events: {len(mine)}")
    if others:
        lines.append(f"Other session events: {len(others)} (not displayed)")
    lines.append("")

    counts = Counter(item["event"] for item in mine)
    lines.append("Recent event counts (current session):")
    lines.extend(f"- {name}: {count}" for name, count in sorted(counts.items()))
    lines.append("")
    lines.append("Last events (metadata only):")
    for item in mine[-15:]:
        details = [f"#{item['seq']}", item["event"]]
        if item.get("tool"):
            details.append(f"tool={item['tool']}")
        if item.get("kind"):
            details.append(f"kind={item['kind']}")
        if item.get("chars") is not None:
            details.append(f"chars={item['chars']}")
        if item.get("status"):
            details.append(f"status={item['status']}")
        details.append(f"scope={item['scope']}")
        details.append(f"turn={item['turn']}")
        lines.append("- " + " | ".join(details))
    lines.extend([
        "",
        "Privacy: prompts, tool results, stream text and reasoning are not retained.",
        "Other-session events are counted but not listed; scope hashes are one-way.",
        "Note: stream observer callbacks are asynchronous; this sequence is diagnostic, not a hard ordering guarantee.",
    ])
    return "\n".join(lines)


def _reset_probe_state_for_tests() -> None:
    global _SEQUENCE
    with _LOCK:
        _EVENTS.clear()
        _SEQUENCE = 0


def register(ctx: Any) -> None:
    """Register documented hooks, the bundled skill, and a diagnostic slash command."""
    if not _SKILL_DIR.is_dir() or not (_SKILL_DIR / "SKILL.md").is_file():
        raise FileNotFoundError(f"Bundled Decision Brief skill missing: {_SKILL_DIR / 'SKILL.md'}")

    ctx.register_skill("decision-brief", _SKILL_DIR / "SKILL.md")
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("pre_tool_call", lambda **kw: _on_pre_tool_call(ctx, **kw))
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("on_stream_delta", _on_stream_delta)
    ctx.register_hook("on_interim_message", _on_interim_message)
    ctx.register_hook("on_stream_end", _on_stream_end)
    ctx.register_command(
        "decision-brief-probe",
        handler=_probe_status,
        description="Show content-free Decision Brief hook diagnostics",
    )


__all__ = ["register"]
