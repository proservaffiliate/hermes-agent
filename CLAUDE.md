# CLAUDE.md

Guidance for Claude Code (and other AI coding assistants) working in this repository.

> **`AGENTS.md` is the canonical, exhaustive development guide** (~1,350 lines:
> contribution rubric, per-subsystem deep dives, config schema, skin engine,
> plugin/skill authoring, profiles, pitfalls). This file is the fast orientation
> layer. When the two disagree, `AGENTS.md` wins. Read the relevant `AGENTS.md`
> section before making a non-trivial change to a subsystem.

## What Hermes Is

Hermes is a personal AI agent that runs one agent core across a CLI, a messaging
gateway (Telegram, Discord, Slack, and ~20 other platforms), an Ink/React TUI, and
an Electron desktop app. It learns across sessions (memory + skills), delegates to
subagents, runs scheduled jobs, and drives a real terminal and browser. It is
extended through **plugins and skills**, not by growing the core.

Two properties shape nearly every design decision:

- **Per-conversation prompt caching is sacred.** A long-lived conversation reuses a
  cached prefix every turn. Anything that mutates past context, swaps toolsets, or
  rebuilds the system prompt mid-conversation invalidates that cache and multiplies
  the user's cost. The only sanctioned exception is context compression.
- **The core is a narrow waist; capability lives at the edges.** Every model tool is
  sent on every API call, so the bar for a new *core* tool is high. New capability
  should usually arrive as a CLI command + skill, a service-gated tool, or a plugin.

Product breadth (platforms, providers, models, desktop/TUI features) is expected to
grow aggressively. The restraint applies to the core agent and the model tool schema.

## Repository Layout

File counts shift constantly — the filesystem is canonical. These are the
load-bearing entry points you will actually edit:

| Path | Role |
| --- | --- |
| `run_agent.py` | `AIAgent` class — the core conversation loop (very large; ~60-param `__init__`) |
| `model_tools.py` | Tool orchestration: `discover_builtin_tools()`, `get_tool_definitions()`, `handle_function_call()` |
| `toolsets.py` | `TOOLSETS` dict and `_HERMES_CORE_TOOLS` — what each platform actually exposes |
| `cli.py` | `HermesCLI` — interactive CLI orchestrator (very large) |
| `hermes_state.py` | `SessionDB` — SQLite session store with FTS5 search |
| `hermes_constants.py` | `get_hermes_home()` / `display_hermes_home()` — profile-aware paths |
| `hermes_logging.py` | `setup_logging()` — agent.log / errors.log / gateway.log |
| `agent/` | Agent internals: provider adapters, memory, caching, compression, context engine |
| `hermes_cli/` | CLI subcommands, setup wizard, plugin loader, curses UI, skin engine |
| `tools/` | Tool implementations, auto-discovered via `tools/registry.py` |
| `tools/environments/` | Terminal backends: local, docker, ssh, modal, daytona, singularity |
| `gateway/` | Messaging gateway — `run.py`, `session.py`, `platforms/`, `builtin_hooks/` |
| `plugins/` | Plugin system: `memory/`, `context_engine/`, `model-providers/`, `kanban/`, … |
| `skills/`, `optional-skills/` | Bundled skills (optional-skills are shipped but inactive by default) |
| `ui-tui/`, `tui_gateway/` | Ink (React) terminal UI + its Python JSON-RPC backend |
| `apps/desktop`, `web/` | Electron desktop app; Vite/React web dashboard |
| `acp_adapter/` | ACP server for VS Code / Zed / JetBrains |
| `cron/` | Scheduler — `jobs.py`, `scheduler.py` |
| `scripts/` | `run_tests.sh`, `release.py`, lint/CI helpers |
| `tests/` | Pytest suite (~17k tests across ~900 files) |
| `website/` | Docusaurus documentation site |

**Import dependency chain** (do not create cycles):

```
tools/registry.py            # no deps — imported by every tool file
   ↑ tools/*.py              # each calls registry.register() at import time
   ↑ model_tools.py          # imports the registry, triggers tool discovery
   ↑ run_agent.py, cli.py, batch_runner.py, tools/environments/
```

**Runtime state** lives under `HERMES_HOME` (default `~/.hermes`):
`config.yaml` (all behavioral settings), `.env` (secrets only), `logs/`, sessions,
skills, plugins.

## Development Environment

```bash
source .venv/bin/activate     # or: source venv/bin/activate
```

`scripts/run_tests.sh` probes `.venv`, then `venv`, then
`$HOME/.hermes/hermes-agent/venv` (for worktrees sharing a venv with the main checkout).

Node workspaces are `apps/*`, `ui-tui`, `ui-tui/packages/*`, `web` (npm, Node >= 20).
Install a single workspace with `npm run install:web` / `install:tui` / `install:desktop`.

## Testing

**Always use `scripts/run_tests.sh` — never call `pytest` directly.** The wrapper
enforces CI parity: it unsets credential env vars, pins `TZ=UTC` and `LANG=C.UTF-8`,
runs `-n auto` xdist workers, and applies the in-tree subprocess-isolation plugin.
Calling `pytest` directly on a many-core machine with API keys set diverges from CI
and has repeatedly caused "works locally, fails in CI" incidents (and the reverse).

```bash
scripts/run_tests.sh                                  # full suite, CI parity
scripts/run_tests.sh tests/gateway/                   # one directory
scripts/run_tests.sh tests/agent/test_foo.py::test_x  # one test
scripts/run_tests.sh -v --tb=long                     # pytest flags pass through
```

Every test file runs in a freshly spawned subprocess (`scripts/run_tests_parallel.py`),
so module-level dicts/sets and ContextVars cannot leak between files.

Test conventions:

- **Never write to `~/.hermes/`.** The autouse `_isolate_hermes_home` fixture in
  `tests/conftest.py` redirects `HERMES_HOME` to a temp dir. For profile tests, also
  monkeypatch `Path.home()` — see `tests/hermes_cli/test_profiles.py`.
- **No change-detector tests.** Do not assert on model-catalog membership, config
  version literals, or enumeration counts — they break on every routine data update
  and add no behavioral coverage. Assert invariants and behavior instead
  (e.g. "every model in the catalog has a context-length entry").
- **Prefer E2E over mocks** for resolution chains, config propagation, security
  boundaries, remote backends, and file/network I/O. Exercise real imports against a
  temp `HERMES_HOME`; mocks hide integration bugs.

## Lint, Typecheck, CI

- `ruff check .` is a **blocking** gate. Lint config is deliberately minimal:
  only `PLW1514` (unspecified-encoding) is selected, because bare
  `open()`/`read_text()`/`write_text()` in text mode falls back to the system locale
  encoding on Windows and silently corrupts non-ASCII content. Always pass
  `encoding="utf-8"` explicitly. (`tests/`, `skills/`, `optional-skills/`, `plugins/`
  are exempt.)
- `python scripts/check-windows-footguns.py --all` is blocking — it bans Windows-unsafe
  primitives (`os.kill(pid, 0)`, `os.killpg`, `os.setsid`, bare `signal.SIGKILL`,
  shebang scripts via subprocess, `open()` without `encoding=`).
- `ty check` runs advisory/diff-based via `scripts/lint_diff.py` (new findings vs. base).
- TypeScript: `npm run --prefix <package> typecheck`; the desktop app must also build.
- Other gates in `.github/workflows/`: `docker-lint`, `osv-scanner`,
  `supply-chain-audit`, `uv-lockfile-check`, `skills-index-freshness`,
  `history-check`, `contributor-check`, `docs-site-checks`.

## Key Conventions

### Configuration: `config.yaml`, not env vars

`.env` is for **secrets only** (API keys, tokens, passwords). Every behavioral
setting — timeouts, thresholds, feature flags, display preferences — belongs in
`config.yaml`. Do not add new `HERMES_*` env vars for non-secret config; bridge to an
internal env var if a mechanism needs one, but point user-facing docs at `config.yaml`.

### Profile-safe paths

Hermes supports profiles: multiple fully isolated instances, each with its own
`HERMES_HOME`. `_apply_profile_override()` in `hermes_cli/main.py` sets `HERMES_HOME`
before any module imports.

```python
# GOOD
from hermes_constants import get_hermes_home
config_path = get_hermes_home() / "config.yaml"

# BAD — breaks profiles
config_path = Path.home() / ".hermes" / "config.yaml"
```

Use `get_hermes_home()` for code paths and `display_hermes_home()` for user-facing
messages and tool schema descriptions. Hardcoded `~/.hermes` was the source of five
bugs in a single PR.

### Adding a tool — settle footprint first

Prefer, in order: extend existing code → CLI command + skill → service-gated tool
(`check_fn`) → plugin → MCP server in the catalog → new core tool (last resort).
For custom or local-only tools do **not** touch core: create
`~/.hermes/plugins/<name>/plugin.yaml` + `__init__.py` and call `ctx.register_tool(...)`.

A genuine core tool takes exactly two files:

1. `tools/your_tool.py` — call `registry.register(name=..., toolset=..., schema=...,
   handler=..., check_fn=..., requires_env=[...])` at module top level. Auto-discovery
   imports any `tools/*.py` with a top-level `register()` call. **All handlers must
   return a JSON string.**
2. `toolsets.py` — add the tool name to `_HERMES_CORE_TOOLS` or a toolset. This step is
   required: registration collects the schema, but a tool is only exposed to an agent
   if it appears in a toolset.

Do not hardcode cross-tool references in schema descriptions (the referenced tool may
be disabled, causing hallucinated calls). Add cross-references dynamically in
`get_tool_definitions()` — see the `browser_navigate` / `execute_code` post-processing
blocks. Agent-level tools (todo, memory) are intercepted in `run_agent.py` before
`handle_function_call()`.

### Cache-aware slash commands

Slash commands that mutate system-prompt state (skills, tools, memory) must default to
**deferred** invalidation — the change takes effect next session — with an opt-in
`--now` flag. `/skills install --now` is the canonical pattern.

### Message-loop invariants

Preserve strict role alternation: never two same-role messages in a row, and never
inject a synthetic user message mid-loop. The system prompt must be byte-stable for
the life of a conversation.

### TypeScript style (desktop, TUI, website, web)

Prefer small nanostores over prop-drilled component state; let each feature own its
atoms. Render from atoms with `useStore`, read in non-rendering actions with
`$atom.get()`. Keep route roots thin and hooks narrow — no god hooks. Prefer
`interface` for public props, extend React primitives (`React.ComponentProps<'button'>`).
Table-driven maps beat condition ladders. `src/app` owns routes and pages, `src/store`
shared atoms, `src/lib` pure helpers.

## Known Pitfalls

- **No new `simple_term_menu` usage.** It has ghost-duplication rendering bugs in
  tmux/iTerm2. New interactive menus use `hermes_cli/curses_ui.py` — see
  `hermes_cli/tools_config.py` for the pattern.
- **No `\033[K` (ANSI erase-to-EOL)** in spinner/display code; it leaks as literal
  `?[K` under `prompt_toolkit`'s `patch_stdout`. Space-pad instead:
  `f"\r{line}{' ' * pad}"`.
- **`_last_resolved_tool_names` in `model_tools.py` is a process global.**
  `_run_single_child()` in `delegate_tool.py` saves/restores it around subagent runs, so
  it can be temporarily stale during child agent execution.
- **The gateway has two message guards.** The base adapter
  (`gateway/platforms/base.py`) queues messages while a session is active, and the
  gateway runner (`gateway/run.py`) intercepts `/stop`, `/new`, `/queue`, `/status`,
  `/approve`, `/deny`. Any new command that must reach the runner while the agent is
  blocked has to bypass **both** and be dispatched inline, not via
  `_process_message_background()` (which races session lifecycle).
- **Squash-merging a stale branch silently reverts recent fixes on `main`.** Bring the
  branch up to date first, then verify with `git diff HEAD~1..HEAD` after merging —
  unexpected deletions are a red flag.
- **Don't wire in dead code without E2E validation.** Unused modules were usually
  unused for a reason.
- **No lazy-reading escape hatches on instructional tools.** Never add
  `offset`/`limit` pagination to tools that load content the agent must read in full
  (skills, prompts, playbooks) — models read page one and skip the rest.

## Subsystem Quick Reference

- **Toolsets** (`toolsets.py`): `browser`, `clarify`, `code_execution`, `cronjob`,
  `debugging`, `delegation`, `discord`, `discord_admin`, `feishu_doc`, `feishu_drive`,
  `file`, `homeassistant`, `image_gen`, `kanban`, `memory`, `messaging`, `moa`, `rl`,
  `safe`, `search`, `session_search`, `skills`, `spotify`, `terminal`, `todo`, `tts`,
  `video`, `vision`, `web`, `yuanbao`. Toggle per platform via `hermes tools` or
  `tools.<platform>.enabled|disabled` in `config.yaml`.
- **Delegation** (`tools/delegate_tool.py`): `delegate_task` spawns a subagent with an
  isolated context + terminal. `role="leaf"` (default) cannot re-delegate;
  `role="orchestrator"` can, bounded by `delegation.max_spawn_depth` (default 2) and
  `max_concurrent_children` (default 3). `background=true` returns a delegation id and
  the result re-enters via the async completion queue — but it is still process-local;
  for restart-durable work use `cronjob` or
  `terminal(background=True, notify_on_complete=True)`.
- **Curator** (`agent/curator.py`): tracks usage of agent-created skills and archives
  stale ones; users never lose skills.
- **Cron** (`cron/`): `jobs.py` + `scheduler.py` for scheduled jobs.
- **Kanban** (`plugins/kanban/`): multi-agent work queue — board dispatcher + worker.
- **Background process notifications**: `terminal(background=true,
  notify_on_complete=true)` runs a gateway watcher that triggers a new agent turn on
  completion. Verbosity: `display.background_process_notifications` in `config.yaml`
  (`all` | `result` | `error` | `off`).

## Contribution Norms

- Prefer fixing the whole bug class — sibling call paths included — not just the one
  site a reporter hit. Reproduce the symptom on current `main` and point at the exact
  line where it manifests.
- Extracting a multi-thousand-line cluster out of `cli.py` / `run_agent.py` /
  `gateway/run.py` into a focused module is wanted work, even when the diff is huge.
- **Verify the premise before calling something a bug.** The most common reason a
  well-written change is rejected is that it treats an intentional design as a gap
  (e.g. profiles are independent islands on purpose). Read the original commit's intent
  (`git log -p -S`) before restricting behavior.
- Not wanted: speculative hooks with no concrete consumer; new core tools where
  terminal + file already suffice; outbound telemetry without opt-in gating; plugins
  that touch core files; third-party vendor integrations in-tree (ship those as
  standalone plugin repos users install into `~/.hermes/plugins/`).
- Preserve contributor credit — cherry-pick/rebase-merge external work rather than
  reimplementing it.

## Further Reading

- `AGENTS.md` — the full development guide (start here for any real change)
- `CONTRIBUTING.md` — contribution process (also `.es.md`)
- `SECURITY.md` — security policy and boundaries
- `README.md` — user-facing overview (also `.es.md`, `.zh-CN.md`, `.ur-pk.md`)
- `docs/` — design docs, session lifecycle, kanban spec, observability, contracts
- `gateway/platforms/ADDING_A_PLATFORM.md` — new messaging platform adapters
- `website/` — the published Docusaurus documentation
