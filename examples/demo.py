#!/usr/bin/env python3
"""Decision Brief — deterministic demo (SIMULATED, no model, no network).

Shows the BEFORE/AFTER transformation hook enrichment applies to a terse
clarify question, plus the creative (image-generation) worked example
following the bundled skill's guidance. All traffic is local and fake; nothing
is sent anywhere and no credentials are used.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("decision_brief_demo", ROOT / "__init__.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SEP = "=" * 78


def transform(question: str, history) -> str:
    found = MODULE._scrubbed_user_context(history)
    enriched, changed = MODULE._enrich_question(question, found)
    return enriched if changed else question


def main() -> int:
    print(SEP)
    print("DECISION BRIEF — SIMULATED DEMO (offline; no model is called)")
    print(SEP)
    print()
    print("[1] Agent decision — terse question, context injected per the skill's structure")
    print()
    history = [
        "user: The project already has Supabase authentication configured, with a "
        "working login flow and session storage. Should I keep it or replace it?"
    ]
    history = [{"role": "user", "content": history[0][5:]}]
    before = "Which authentication approach should I use?"
    after = transform(before, history)
    print("BEFORE:")
    print(f"  {before}")
    print()
    print("AFTER (as the agent would phrase the clarify question):")
    for line in after.splitlines():
        print(f"  {line}")
    print()
    print("(The agent would still add a Recommendation only when the evidence")
    print(" supports one, using native clarify choices. Never invented evidence.)")
    print()
    print(SEP)
    print("[2] Image generation — creative direction before image_generate")
    print()
    history = [{"role": "user", "content": "Create a cinematic photograph of a woman outside a luxury hotel."}]
    before = "Which lighting direction should I use?"
    after = transform(before, history)
    print("BEFORE:")
    print(f"  {before}")
    print()
    print("AFTER (skill-shaped brief the agent asks with — illustrative):")
    print("  Creative direction — hotel exterior lighting")
    print("  What I found: the subject is unspecified; night vs golden hour changes")
    print("  the image's contrast, color and atmosphere, not the scene layout.")
    print("  Why it matters: lighting is the choice that most changes the cinematic read.")
    print("  Choices:")
    print("    - Night, warm practical lighting, slightly wet street (recommended)")
    print("    - Golden hour, warmer editorial look")
    print("    - Daylight, cleaner commercial feel")
    print("    - You decide")
    print()
    print("(The agent then incorporates the choice into the native image_generate")
    print(" prompt itself. This plugin does not generate images in this demo.)")
    print()
    print(SEP)
    print("Hook output for the same transformation, via pre_tool_call:")
    print()

    class FakeCtx:
        def get_config(self, key, default=None):
            return default

        def register_hook(self, name, fn):
            self.fn = getattr(self, "fn", {})
            self.fn[name] = fn

        def register_skill(self, name, path):
            return None

        def register_command(self, name, handler, description=""):
            return None

    ctx = FakeCtx()
    MODULE.register(ctx)
    result = ctx.fn["pre_tool_call"](
        tool_name="clarify",
        args={"questions": [{"question": before, "choices": ["Night", "Golden hour", "Daylight", "You decide"]}]},
        session_id="demo-session",
        turn_id="demo-turn",
    )
    q = result["args"]["questions"][0]
    print("  action :", result["action"])
    print("  choices:", q["choices"], "(unchanged by design)")
    print("  question:")
    for line in q["question"].splitlines():
        print("   ", line)
    print()
    print("Demo complete. Nothing was sent anywhere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
