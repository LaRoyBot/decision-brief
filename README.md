# Decision Brief — a human decision layer for Hermes Agent

> Decision Brief helps Hermes pause at consequential choices and present a compact, understandable decision before continuing. It applies to both engineering/agent decisions and creative workflows such as image generation.

## What it does

- asks only when a decision is consequential (ambiguous, hard to reverse, or user-preference-dependent)
- explains the decision compactly: **Decision / What I found / Why it matters / Recommendation**
- provides a recommendation when evidence supports one
- uses Hermes's native `clarify` panel — it never invents its own UI
- supports creative decisions around image generation (lighting, composition, mood) before `image_generate`
- preserves native clarify choices, order, and `multi_select` — always
- never captures hidden reasoning
- never stores raw user content (prompts, tool results, stream text)

## Example 1 — Agent decision

```text
User: "Set up auth — keep Supabase or custom?"

Decision Brief:
Decision: Authentication architecture
What I found: The choice affects implementation complexity,
maintenance, and integration effort.
Why it matters: Changing auth architecture later can be expensive.
Recommendation: Keep Supabase if the existing stack already depends on it.

[Keep Supabase] [Build custom]
```

## Example 2 — Creative decision

```text
User: "Create a cinematic full-body photograph outside a luxury hotel."

Decision Brief can surface a meaningful creative choice such as:

Night vs. golden hour?

Why it matters: The lighting changes the atmosphere,
contrast, and perceived luxury of the scene.

[Golden hour — recommended]
[Night]
```

The creative decision is skill-guided. Provider-dependent live generation was unavailable during validation because the provider returned HTTP 402.

## Validation status

```text
13 tests — PASS
python -m compileall -q . — PASS
hermes plugins doctor — PASS
hermes plugins validate — PASS
```

> Live provider-dependent clarify/image-generation validation was blocked by OpenRouter HTTP 402 during the validation window. The plugin does not claim those provider flows were live-tested.

## Architecture

```text
User request
    ↓
Hermes skill guidance (bundled decision-brief skill)
    ↓
Consequential decision detected
    ↓
Native Hermes clarify
    ↓
User approval
    ↓
Hermes continues normally
```

Plugin hook:

```text
pre_tool_call
    ├── clarify → lightweight question enrichment (choices untouched)
    └── image_generate → observed integration point (never blocked or rewritten)
```

**Image generation is not automatically blocked or rewritten by the plugin.** The skill is responsible for getting the user's approved creative direction into the `image_generate` prompt.

## Install

Portable / catalog install:

```bash
hermes plugins install <owner>/decision-brief
hermes plugins enable decision-brief
```

Local development:

```bash
cp -r decision-brief <HERMES_HOME>/plugins/decision-brief
hermes plugins enable decision-brief
```

Then, interactively:

```text
/decision-brief:decision-brief
<ask a consequential question — the agent will ask one focused clarify, or decide solo>
```

## Notes

- `/decision-brief-probe` shows content-free diagnostics (event counts, hashed scope/turn tokens, current-vs-other session split). Profile-scoped — the profile's gateway is shared across its sessions.
- No telemetry, no external services, no persistent conversation logs, no hidden reasoning capture.
