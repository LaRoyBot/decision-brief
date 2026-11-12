from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("decision_brief_spike", ROOT / "__init__.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeContext:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.hooks = {}
        self.skills = []
        self.commands = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def register_skill(self, name, path):
        self.skills.append((name, Path(path)))

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler


class DecisionBriefMVPTests(unittest.TestCase):
    def setUp(self):
        MODULE._reset_probe_state_for_tests()

    def test_imports_and_registers_documented_surface(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        self.assertEqual(
            set(ctx.hooks),
            {
                "pre_llm_call", "pre_tool_call", "post_tool_call",
                "on_stream_delta", "on_interim_message", "on_stream_end",
            },
        )
        self.assertEqual(ctx.skills[0][0], "decision-brief")
        self.assertTrue(ctx.skills[0][1].is_file())
        self.assertTrue((MODULE._PLUGIN_DIR / "skills" / "decision-brief" / "SKILL.md").is_file())
        self.assertIn("decision-brief-probe", ctx.commands)
        self.assertIn("decision-brief", ctx.commands)
        self.assertIn("Decision Brief active", ctx.commands["decision-brief"](""))

    def test_clarify_enrichment_on_by_default_choices_untouched(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        result = ctx.hooks["pre_tool_call"](
            tool_name="clarify",
            args={
                "questions": [
                    {"question": "Which auth should I use?", "choices": ["Keep Supabase", "Rewrite custom"], "multi_select": False},
                    {"question": "Second question?", "choices": ["A", "B"]},
                ],
            },
            session_id="sess-default",
        )
        self.assertEqual(result["action"], "modify")
        questions = result["args"]["questions"]
        for index, item in enumerate(questions):
            self.assertTrue(item["question"].startswith("Decision: "))
            self.assertLessEqual(len(item["question"]), 780)
        self.assertEqual(questions[0]["choices"], ["Keep Supabase", "Rewrite custom"])
        self.assertEqual(questions[0]["multi_select"], False)
        self.assertEqual(questions[1]["choices"], ["A", "B"])

    def test_clarify_contextualized_question_left_unchanged(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        contextualized = (
            "Decision: which auth approach should I use?\n"
            "What I found: the project already has Supabase auth wired in config and login flow.\n"
            "Why it matters: replacing it breaks existing sessions and config."
        )
        result = ctx.hooks["pre_tool_call"](
            tool_name="clarify",
            args={"questions": [{"question": contextualized, "choices": ["Keep", "Replace"]}]},
            session_id="sess-contextual",
        )
        self.assertIsNone(result)

    def test_clarify_fail_open_on_invalid_args(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        self.assertIsNone(ctx.hooks["pre_tool_call"](tool_name="clarify", args=None, session_id="sess-x"))
        self.assertIsNone(ctx.hooks["pre_tool_call"](tool_name="clarify", args={"questions": "not-a-list"}, session_id="sess-x"))
        self.assertIsNone(ctx.hooks["pre_tool_call"](tool_name="clarify", args={"questions": []}, session_id="sess-x"))
        self.assertIsNone(ctx.hooks["pre_tool_call"](tool_name="clarify", args={"questions": [123, None]}, session_id="sess-x"))
        self.assertIsNone(ctx.hooks["pre_tool_call"](tool_name="clarify", args={"questions": [{}]}, session_id="sess-x"))

    def test_clarify_enrichment_scrubs_secret_context(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        found = MODULE._scrubbed_user_context([{"role": "user", "content": "here is my key sk-abcDEFGH1234567890ABCDE and the question"}])
        self.assertIsNone(found)

    def test_clarify_enrichment_uses_scrubbed_context_when_clean(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        found = MODULE._scrubbed_user_context(
            [{"role": "user", "content": "The project already has Supabase authentication configured and a working login flow."}]
        )
        self.assertIsNotNone(found)
        self.assertIn("Supabase", found)

    def test_marker_preserved_and_choices_unchanged(self):
        ctx = FakeContext(settings={"probe_marker": True})
        MODULE.register(ctx)
        original = {
            "questions": [
                {"question": "Which setting?", "choices": ["Night", "Day"], "multi_select": False},
            ],
            "other_arg": "preserve-me",
        }
        result = ctx.hooks["pre_tool_call"](
            tool_name="clarify", args=original, session_id="sess-marker", turn_id="turn-marker"
        )
        self.assertEqual(result["action"], "modify")
        modified = result["args"]["questions"]
        self.assertTrue(modified[0]["question"].startswith(MODULE._MARKER))
        self.assertEqual(modified[0]["choices"], ["Night", "Day"])
        self.assertEqual(modified[0]["multi_select"], False)
        self.assertEqual(original["questions"][0]["question"], "Which setting?")

    def test_image_generate_observed_not_modified(self):
        ctx = FakeContext(settings={"probe_marker": True})
        MODULE.register(ctx)
        prompt = "cinematic hotel exterior at night"
        result = ctx.hooks["pre_tool_call"](
            tool_name="image_generate", args={"prompt": prompt, "aspect_ratio": "portrait"},
            session_id="sess-image", turn_id="turn-image",
        )
        self.assertIsNone(result)  # hook passes through; prompt never rewritten
        status = ctx.commands["decision-brief-probe"]("")
        self.assertIn("image_generate.pre", status)
        self.assertNotIn(prompt, status)

    def test_stream_observer_discards_text_and_nontext_payloads(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        unique_text = "DO_NOT_RETAIN_THIS_STREAM_SECRET"
        ctx.hooks["on_stream_delta"](
            delta=unique_text, kind="text", session_id="sess-d", turn_id="turn-d"
        )
        ctx.hooks["on_stream_delta"](
            delta="private reasoning payload", kind="reasoning", session_id="sess-d", turn_id="turn-d"
        )
        status = ctx.commands["decision-brief-probe"]("")
        self.assertIn("stream.text_delta", status)
        self.assertIn("stream.nontext_ignored", status)
        self.assertNotIn(unique_text, status)
        self.assertNotIn("private reasoning payload", status)
        self.assertNotIn(unique_text, repr(list(MODULE._EVENTS)))
        self.assertNotIn("private reasoning payload", repr(list(MODULE._EVENTS)))

    def test_post_tool_records_clarify_then_image_order(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        ctx.hooks["post_tool_call"](
            tool_name="clarify", result="SENSITIVE_USER_ANSWER", status="success",
            session_id="sess-e", turn_id="turn-e",
        )
        ctx.hooks["pre_tool_call"](
            tool_name="image_generate", args={"prompt": "not-retained"},
            session_id="sess-e", turn_id="turn-e",
        )
        status = ctx.commands["decision-brief-probe"]("")
        timeline = status.split("Last events (metadata only):", 1)[1]
        self.assertLess(timeline.index("clarify.post"), timeline.index("image_generate.pre"))
        self.assertNotIn("SENSITIVE_USER_ANSWER", status)
        self.assertNotIn("not-retained", status)

    def test_events_tagged_distinct_scopes(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        hook = ctx.hooks["pre_tool_call"]
        hook(tool_name="clarify", args={"questions": []}, session_id="session-one", turn_id="t1")
        hook(tool_name="clarify", args={"questions": []}, session_id="session-two", turn_id="t2")
        scopes = [event["scope"] for event in MODULE._EVENTS]
        self.assertEqual(len(scopes), 2)
        self.assertNotEqual(scopes[0], scopes[1])

    def test_probe_filters_to_current_session_scope(self):
        ctx = FakeContext()
        MODULE.register(ctx)
        hook = ctx.hooks["pre_tool_call"]
        hook(tool_name="clarify", args={"questions": [{"question": "Q one?"}]}, session_id="session-alpha", turn_id="t-a")
        hook(tool_name="clarify", args={"questions": [{"question": "Q two?"}]}, session_id="session-beta", turn_id="t-b")
        status = ctx.commands["decision-brief-probe"]("", session_id="session-alpha")
        self.assertIn("profile-scoped", status.lower())
        self.assertIn("Current session events: 1", status)
        self.assertIn("Other session events: 1 (not displayed)", status)
        self.assertNotIn("Q one?", status)
        self.assertNotIn("Q two?", status)

    def test_enrichment_marker_coexist(self):
        ctx = FakeContext(settings={"probe_marker": True})
        MODULE.register(ctx)
        result = ctx.hooks["pre_tool_call"](
            tool_name="clarify",
            args={"questions": [{"question": "Which venue?", "choices": ["Rooftop", "Beach club"]}]},
            session_id="sess-coexist",
        )
        question = result["args"]["questions"][0]["question"]
        self.assertTrue(question.startswith(MODULE._MARKER))
        self.assertIn("Decision:", question)
        self.assertEqual(result["args"]["questions"][0]["choices"], ["Rooftop", "Beach club"])


if __name__ == "__main__":
    unittest.main()
