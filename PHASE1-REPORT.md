# Decision Brief — Phase 1 feasibility report

**Phase 1 live validation environment: disposable `HERMES_HOME` (`phase1-live\hermes-home`), isolated from the active profile. Plugin source unmodified. No credentials copied, printed, or used from the active profile; provider keys resolve from environment variables. All models were reached through the operator's local proxy (`http://localhost:20128/v1`) — "models from on here"; no external service was added.**

**Headline result:** every check that can run in this environment passes; the interactive agent turns required for the clarify/image/marker flows are blocked by free-tier provider capacity (all free routes are drained, rate-capped, or credentialless), not by the plugin. One live interactive turn "completed" early in the day via `openrouter/openrouter/free` (answered in prose, no clarify); since then the free pools are exhausted. The probe command itself was verified end to end live: it ran, it printed the plugin's metadata-only event timeline, and it proved that no prompt/result/reasoning content is ever retained (noting the shared-gateway scope-sharing observation below).

**Verdict: NO-GO for Phase 2 MVP on today's evidence. GO to re-run the three blocked interactive tests once a model can serve this environment's interactive footprint.**

## Environment and isolation

- Disposable profile at `phase1-live\hermes-home`; the active profile was never modified, authed-to, or copied from.
- Provider keys resolve from environment (`NINE_ROUTER_API_KEY`); the active profile's 9router key was never copied. `OPENROUTER_API_KEY` present but account at HTTP 402 (insufficient credits).
- Interactive sessions spawn one profile-scoped local gateway per availability window (600s idle exit); all interactive runs in this validation used it.
- Telemetry: first interactive start showed the consent dialog; answered with the safe default (`No thanks` — shared metrics off). `telemetry.shared_metrics.enabled: false` persisted in disposable profile.

## Installed Hermes under test

- Hermes Agent v0.22.0+9589.gb200f5b (2026.9.24), stable, HEAD detached at `b200f5bc60`. Local source tree `E:\hermes\hermes-agent`.

## Results

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | `python -m unittest discover -s tests -v` | **PASS** 7/7 (re-verified) | marker opt-in & choices preserved; scope hashing; clarify→image order; image prompt untouched; hook/skill/command registration |
| 2 | `python -m compileall -q .` | PASS (exit 0) | |
| 3 | `hermes plugins doctor <plugin-dir>` | PASS — discovery, manifest, import, registration; 6 hooks | |
| 4 | `hermes plugins enable decision-brief` | PASS | |
| 5 | `hermes plugins validate <plugin-dir>` | PASS — incl. security scan, no core override | |
| 6 | Bundled skill discovered (`<available_skills>`) | PASS live (exact excerpt below) | |
| 7 | `/decision-brief:decision-brief` invokes + injects skill, live | PASS — `⚙️ /decision-brief:decision-brief` → `[IMPORTANT: …skill content is loaded below]` → `⚡ Loading skill: decision-brief:decision-brief` + `[Skill directory: …plugins\decision-brief\skills\decision-brief]` (see `pty-s1-skill-clarify-probe-skill-invoked.txt`) | |
| 8 | Live clarify panel rendered by an available model | **BLOCKED** | six interactive runs across two free providers (`nous/stepfun/step-3.7-flash:free`, `openrouter/openrouter/free`) and all others died in the 429/retry loop; zero interactive turns completed under Nous fair-share since the free pools drained. The single interactive completion observed (Run B, 2026-11-12T00:34:55 local, `api_calls=1`, 365-char prose answer, no clarify) was via `openrouter/openrouter/free` before its daily cap (`free-models-per-day`, `X-RateLimit-Remaining: 0`, reset 2026-11-12T00:00Z). |
| 9 | Clarify interception + `[DECISION BRIEF SPIKE]` marker, live (`probe_marker: true`) | **BLOCKED** (config verified: setting persists; plugin flip verified offline by unit test only) | re-run (`s2-marker`) sent the webinar question at 01:35; provider never served it; panel never rendered; `probe_marker: true` was live in the disposable profile for the run. |
| 10 | `/decision-brief-probe` invocation + timeline content | **PASS** (with caveats) | ran live after aborting a stalled turn: printed event counts (`pre_llm_call` 6→7, `stream.end` 23, `stream.text_delta` 1/0), full timestamps of hook firings, per-event `scope=`/`turn=` hashes, lengths only (e.g. `chars=15` for "Say exactly: OK"), zero prompt/result/reasoning content. Caveat: it QUEUES like any slash command while an agent turn is active — it only ran after Ctrl+C aborted the provider-stalled turn. Caveat 2: timeline never included clarify/image events (turn never advanced). |
| 11 | Image-generation sequence (clarify → answer → `image_generate` args → guard block, no cost) | **NOT TESTED** live (provider refused the clarify turn; no agent ever progressed to the image tool) | No-cost guard `phase1-image-guard` (test-only; installed, doctor-passed, enabled) locally block-tested: machine-verified it returns `{"action":"block",...}` for `image_generate` and pass-through for other tools; logs `tool_name`, `prompt_chars`, `turn_id` only (never prompt text). Actual provider generation: **BLOCKED** (HTTP 402 insufficient credits). Guard disabled post-validation: `hermes plugins disable phase1-image-guard` → `disabled user 0.0.1`. |
| 12 | Two-session session isolation | **PARTIAL PASS — with a shared-gateway finding** | Distinct scope hashes confirmed live across two interactive sessions in the same profile (s4a `pty-s4a-isolation-a` vs s4b `pty-s4b-isolation-b`): hashes for the two "Say exactly: OK" turns differ (`97108617` / `894be91b` `3be5c25d` family), and no content of any kind crosses sessions (plugin retains zero content by design; probe prints only lengths + hashes). **Finding:** the interactive profile uses ONE shared, long-lived gateway process; the plugin's in-memory deque therefore accumulates across sessions (s4b's probe showed s4a's events #43–55 plus its own new ones). Cross-session content is never exposed (nothing but metadata is retained), but `/decision-brief-probe` is NOT session-scoped — in a shared gateway it reveals profile-wide aggregates. Not a Phase-1 defect (metadata-only by design), but Phase 2 must either hash-scope the probe output or document it as profile-global. Plugin data persistence: none anywhere on disk (verified by file sweep; `plugins/` and logs contain no prompt text). |

## Check 1 — Skill discovery discrepancy (resolved: stale docs, intended behavior)

- Docs (`website/docs/developer-guide/plugins/index.md`): "Plugin skills are **not** listed in the system prompt's `<available_skills>` — they're opt-in explicit loads." — **stale**.
- Installed build lists them: `agent/prompt_builder.py::_plugin_skill_prompt_rows()` — "The qualified `plugin:skill` name is exactly what `skill_view` resolves … this is their one path into `<available_skills>`". Introduced upstream in `19cb1cbfed` (2026-10-07, `fix: disclose enabled plugins' registered skills in the system prompt's available_skills index`); this build (b200f5bc60) is post-commit.
- Plugin-manager contract agrees: `hermes_cli/plugins_content.py::register_skill(…)` — "listed by `skills_list` and in the system prompt's `<available_skills>` while the plugin is enabled."
- **Observed live** (exact excerpt from the running system prompt):
  ```
  - obsidian: Read, search, create, and edit notes in the Obsidian vault.
  - decision-brief:decision-brief
  productivity:
  ```
- Discovery ≠ activation: listing is metadata; the skill activates only on explicit invocation (`/decision-brief:decision-brief`, verified end-to-end incl. content injection). Upstream documentation, not the plugin, needs the fix.

## Check 3 — Model / tool-use distinction (evidence, not excuses)

Per-run requested model (from logs, status bar, error dumps):

- Runs A/C/D/E/F (01:07Z, 00:58Z, 00:40Z, 01:15Z, 01:33Z): `nous/stepfun/step-3.7-flash:free` — zero interactive completions; upstream 429 `FreeUsageLimitError` ("fair-share rate limit … retry_after": 504; "reset after 4m 16s"); auto-recovery cycles 2/5 then 4/5; retrying 128s/256s/300s.
- Run B (00:33Z): `openrouter/openrouter/free` — completion in 14.6s (`api_calls=1`, prose answer, no clarify call by model choice — the skill wasn't loaded correctly for that attempt at that point).
- Runs C–E (00:40Z/00:58Z/01:07Z): same model → `503 [openrouter/openrouter/free] [429]: "Rate limit exceeded: free-models-per-day … X-RateLimit-Limit: 50, X-RateLimit-Remaining: 0"`.
- Run F (01:15Z): `nous/stepfun/step-3.7-flash:free` — stalled for the entire 15-minute window, `retrying in 300s (attempt 2/3)`; `/decision-brief-probe` sat queued in the queue indicator.
- `cl/*` pools: 401/402/404 upstream (`cl/thinkingmachines/inkling-2-small:free` → "model not supported"; `cl/z-ai/glm-5.2:free` → 401). `oc/*` pools: all 429 FreeUsageLimitError. `my-combo`: HTTP 400. `gh/gpt-5.6-luna-free-auto`: 400. `ocz/muse-spark-1.3-contributor-free`: 404 "No active credentials". bare `muse-spark-1.3-contributor-free`: 403. All `openrouter/*:free`: same shared daily cap (50/day) — exhausted.
- Where the model could not be observed deciding anything: runs A/C/D/E/F never produced a first token; Run B produced one and chose prose. **No plugin hook failure exists anywhere in the logs** — `errors.log` contains provider 5xx/429/404 only, never a decision-brief trace. The plugin was never at fault; the environment simply cannot deliver a turn right now.
- Note: Hermes defers some tools behind `tool_search`/`tool_describe`/`tool_call` (20–21 schemas materialized per turn); a turn failure at the provider stage invalidates no conclusion about the plugin's hook set, which is verified statically and offline.

## Test-only scaffolding

`phase1-image-guard` (this directory's parent: `plugins\phase1-image-guard\`) is the ONLY artifact outside the original bundle. Purpose: block `image_generate` **before** the provider is invoked so the clarify → image workflow can be validated at zero cost. Contains no prompt text; logs only `tool_name`, `prompt_chars`, `turn_id`. Disabled afterwards (`plugins disable` — output above). It is not part of `decision-brief`; it is not Phase 2; it will be deleted when the disposable profile is wiped.

Recorded anomaly (CLI, not plugin): after `hermes plugins enable phase1-image-guard`, `plugins.enabled` was rewritten to `[phase1-image-guard]`, silently dropping `decision-brief`; re-running `hermes plugins enable decision-brief` restored both entries. Treated as an enable/rewrite ordering artifact of the disposable profile's config. Mitigation applied: `plugins list --plain --no-bundled` checked after every enable.

## Provider quota — remediation for the re-run

Any one of these unlocks the full re-run without changing anything else:
1. Paid `openrouter/*` route on a funded account, or any paid Nous pool (`nous/*` at paid tier — quotas are fair-share, paid tiers are per-token), or OpenCode Go subscription (`oc/*` full capacity), or a local model server with tool-calling.
2. Timeouts for interactive turns: the current 429 windows usually close within ~5 minutes; Hermes' own auto-recovery (5 cycles × 120–600s) needs only one successful attempt to unwind the whole clarify flow.

## Go / no-go

**NO-GO for Phase 2 on today's evidence.** Nothing has demonstrated model-follow-through for the clarify-first behavior, hook ordering under a real clarify event, marker interception live, or image-prompt incorporation. The plugin is verified structurally sound and its skill-invocation path works end-to-end; the rest is environment-limited, not plugin-limited.

**GO for re-running the four blocked tests when a provider exists** — the disposable profile, PTY driver, and scenarios are complete and ready:
- clarify flow + panel screenshot: `pty_driver.py scenarios/scenario-s1.json` (marker=false) then `scenario-s2.json` with `probe_marker: true`;
- no-cost image sequence: `scenario-s3.json` (guard re-enabled, provider call blocked pre-dispatch);
- probe timeline with clarify events: same run, `/decision-brief-probe` after the clarify completes;
- two-session isolation: `scenario-s4a.json` / `scenario-s4b.json` (after provider availability).

## What was NOT done / not proven

- clarify before `image_generate` (agent following the skill) — **not observed** (provider).
- marker live in a rendered clarify panel — **not observed** (provider).
- hook event ordering with clarify+image tools — **not observed** (provider); unit-order PASS only.
- isolation across two *distinct-profile* profiles — **not run** (single disposable profile met Phase 1's isolation ask; distinct-profile isolation wasn't a requirement of this spike).

## Appendix — evidence map

| Artifact | Path |
|---|---|
| PTY driver + scenarios | `phase1-live/pty_driver.py`, `phase1-live/scenario-s{1,2,3,4a,4b}.json` |
| Interactive raw transcripts | `phase1-live/pty-*.log`, `pty-*-events.jsonl`, `pty-*-{boot,skill-invoked,clarify-panel,after-answers,final,probe}.txt` |
| Hermes logs (disposable profile) | `hermes-home/logs/gateway.log`, `hermes-home/logs/errors.log` |
| System prompt dump with `<available_skills>` | `phase1-live/sys_prompt.txt` |
| Image guard source | `hermes-home/plugins/phase1-image-guard/{plugin.yaml,__init__.py}` |
| This report | `phase1-live/decision-brief/PHASE1-REPORT.md` |
