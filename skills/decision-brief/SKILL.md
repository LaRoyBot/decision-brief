---
name: decision-brief
description: Make consequential agent and creative decisions understandable before acting.
version: 0.2.0
metadata:
  hermes:
    tags: [decision-making, approvals, creative-direction, image-generation, workflow]
    category: productivity
---

# Decision Brief — MVP

Decision Brief is a decision layer, not a questionnaire generator.

Its job: **before Hermes asks the user to make an important decision, make that decision understandable** — what was found, why it matters, what the choices mean, and (when justified) what Hermes recommends.

It works for both kinds of work:

- **Agent decisions** — architecture, implementation, research, deploys, trade-offs, irreversible actions.
- **Creative decisions** — image generation, design, visual direction, wardrobe, composition.

It uses Hermes's native `clarify` tool for questions and Hermes's native `image_generate` tool for follow-through. No external services, no extra model calls, no stored history beyond the diagnostic metadata in `/decision-brief-probe`.

## The decision rule

Ask only when a choice is **consequential**:

- materially changes the result, cost, risk, or direction;
- is ambiguous, hard to reverse, or user-preference-dependent;
- or the user's approval is required before spending money, deleting things, or breaking a public interface.

Otherwise, **decide and continue**. Reversible, low-impact, ordinary art-direction/implementation calls: make a reasonable choice, state it briefly, proceed. Never turn a simple task into a questionnaire.

## Before asking

1. Check the user's request, references, and findings already established in the conversation.
2. Do not re-ask for what the user already supplied.
3. Identify the *smallest* set of decisions that materially matter — at most a few questions, one `clarify` call, each question self-contained.
4. If the user says "you decide", "surprise me", "proceed", or similar, use your judgment and continue.

## Writing a decision brief

Each question must stand on its own. Structure it compactly:

- **Decision** — what needs to be decided now.
- **What I found** — only relevant, user-visible evidence from the conversation or repo. If there is none, say so plainly.
- **Why it matters** — the concrete consequence of the choice.
- **Recommendation** — only when the evidence supports one. Prefer the first choice as your recommendation.

Then use native `clarify` choices. Offer distinct, actionable options. Prefer one concise recommendation over a preferences survey. Preserve the user's own specified options; never invent facts, evidence, or options the user did not allow. Keep questions short (**roughly ≤ 800 characters**).

Never expose hidden reasoning, tool internals, prompts, or chain-of-thought. Never reveal secrets, keys, tokens, passwords, or private data. If no safe context is available, ask a concise question without pretending to know more.

## Agent decisions (code, research, ops)

Good candidates:

- Two or more viable technical approaches with different cost/risk/direction.
- Destructive or irreversible steps (drop tables, rotate keys, force-push, delete data).
- Deploys, migrations, auth changes, new dependencies with real weight.
- Spend, budget, publishing, messaging someone else's systems.

Poor candidates: naming a variable, formatting, choosing a lint config, picking a reversible scaffold. Just decide.

## Creative decisions (image generation, design)

When preparing an image-generation request, ask about the decisions that **materially change the image**, e.g.:

- setting / background
- time of day / lighting (golden hour vs night vs daylight)
- mood / style (editorial, cinematic, candid, studio)
- composition / camera angle / subject framing
- wardrobe / accessories that change the read of the subject

You decide the rest yourself — ordinary art direction is not a question. Do not ask about every visual detail.

Example (agent prompt):

User: "Create a cinematic photograph of a woman outside a luxury hotel."

Ask (one question, ≤ 4 choices):

**Creative direction — hotel exterior palette.**

I'm leaning toward nighttime with warm practical lighting and a slightly wet street: stronger contrast, more cinematic/upscale atmosphere, better for the "luxury" read.

**Why it matters**

Golden hour gives a warmer editorial look; night gives contrast and atmosphere; daylight is cleaner and more commercial.

- Night — recommended (most cinematic)
- Golden hour
- Daylight
- You decide

After the user answers, incorporate the choice into the final `image_generate` prompt yourself. Do not silently override the user's choice. Do not ask again about the direction you just set. High-impact remaining ambiguity → one clarify, never a questionnaire. After the direction is approved, proceed to `image_generate` unless another material ambiguity remains.

## Approval and follow-through

An approval applies to the specific decision asked. It does not transfer to unrelated actions. After the user decides, execute the chosen direction and report the outcome; do not re-litigate the question.

## Native surfaces only

- Questions: Hermes `clarify` tool (`questions[]` with string `question`, optional `choices`, `multi_select`).
- Images: Hermes `image_generate` (uses native provider; may be unavailable without provider access).
- Do not create fake approval UI or extra modals — the native clarify panel is the surface.

## Honest limitations

- The plugin/skill cannot force a model to ask; it guides behavior and provides an interception point.
- `/decision-brief-probe` shows metadata only; it is profile-scoped (the profile's gateway is shared across its sessions), not strictly per-session.
- Enrichment of terse questions is deterministic text shaping only; it is never a source of invented evidence.

## Privacy

No prompts, results, stream text or reasoning are stored by the plugin. Event metadata only (lengths, statuses, hashed ids, counts).
