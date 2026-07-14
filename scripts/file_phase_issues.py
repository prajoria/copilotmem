#!/usr/bin/env python3
"""
scripts/file_phase_issues.py — bulk-file the Phase A/B batch of issues on
prajoria/copilotmem, attach each to project #6, and set field values.

Usage:
    python scripts/file_phase_issues.py --dry-run    # preview, no API calls
    python scripts/file_phase_issues.py --live       # actually file

Idempotency: refuses to run --live if any of the target issue titles already
exist as open issues on the repo. This prevents accidental double-filing.

Tracking issue: https://github.com/prajoria/copilotmem/issues/6
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = "prajoria/copilotmem"
PROJECT_JSON = Path(__file__).parent / "copilotmem_project.json"


# --------------------------------------------------------------------------
# Batch definition. Each dict is one issue.
#
# - `key` is a local identifier used only within this file to wire
#   `depends_on` chains before real GitHub issue numbers exist.
# - `title` is the exact GitHub issue title.
# - `labels` is a list of label names (must exist on the repo).
# - `area/priority/type/phase` are field-option names, resolved to option IDs
#   via copilotmem_project.json.
# - `depends_on` is a list of local `key`s. On the second pass the script
#   replaces `{DEPENDS:key,key,...}` placeholders in the body with
#   the real `Depends on #NN, #NN` string.
# - `body` is the initial issue body. Concise on purpose — the point of
#   the batch is to establish tracking, not to pre-write full specs.
# --------------------------------------------------------------------------

BATCH: list[dict[str, Any]] = [
    # -------- Phase A: doc frame revisions --------
    {
        "key": "A1",
        "title": "docs(prd): v0.5 — three-submodule aggregator model + single-auth-chain rule",
        "labels": ["copilotmem", "type-task", "area-docs", "phase-0", "priority-p0"],
        "area": "Docs", "priority": "P0", "type": "Task", "phase": "Phase 0",
        "depends_on": [],
        "body": """## Purpose

Revise `docs/PRD.md` from v0.4 → v0.5 to reflect two architectural decisions
made in the session that produced #6:

1. **Three-submodule aggregator model** — `copilot-api`, `claude-mem`, and `headroom`
   are all git submodules under `vendor/`. Same-language ones are imported
   in-process; language-mismatched ones (headroom) run as supervised subprocesses.
   Replaces the v0.4 "port everything except copilot-api" plan.

2. **Single-auth-chain rule** — no caller of any CopilotMem component may require
   a Claude/Anthropic OAuth login separate from the Copilot upstream token.
   The memory summarizer calls the proxy itself with
   `X-CopilotMem-Extensions: none` as a recursion guard.

## Sections to revise

- **§7.2** (subsection rewrites 7.2.2, 7.2.3, 7.2.4) — aggregator model.
- **New §7.2.5** — single-auth-chain rule, cited by contract test in B4b.
- **§7.5** — namespace table adds subprocess IPC row + recursion-guard header row.
- **§10.5** — "single binary" → "single install bundle".
- **§6** — memory footprint budget adjusted for subprocess overhead.
- **§12** — success criteria reframed for install bundle.
- **§14** — Phase 1/2 timelines shrink (wrap-vs-port).
- **§5.2** — strengthened to reference the contract test.
- **§13** — recursion-loop risk elevated to Critical.
- **Header** — Version bumped to 0.5; Last updated to today.

## Exit criteria

- [ ] All above sections revised.
- [ ] PRD reads coherently end-to-end (no v0.4 leftovers contradicting v0.5).
- [ ] Diff proposed for review before commit.
- [ ] Commit `docs(prd): v0.5 — aggregator model + single-auth-chain rule (#NN)` merged.

## Depends on

Nothing. This is the top of the chain — everything else follows from a settled PRD.

## Refs

- Root epic: #3
- Rule that requires this issue: #1
- Session context: aggregator discussion, auth-chain discussion (in-session)
""",
    },
    {
        "key": "A2",
        "title": "docs(session-start): reflect aggregator strategy + auth-chain rule",
        "labels": ["copilotmem", "type-task", "area-docs", "phase-0", "priority-p1"],
        "area": "Docs", "priority": "P1", "type": "Task", "phase": "Phase 0",
        "depends_on": ["A1"],
        "body": """## Purpose

Update `SESSION-START.md` to match the PRD v0.5 landed in A1. Without this,
a fresh session reading SESSION-START gets the old strategy and drifts.

## Sections to revise

- **§4 hybrid-strategy table** — becomes uniform-submodule table with an
  "integration mode" column (in-process vs. supervised subprocess).
- **§8.4** — remove "Do not vendor claude-mem or headroom" prohibition;
  add "Do not import auth-touching files from vendored submodules"
  (points at new §9.6).
- **New §9.6 "Auth-chain audit for vendored code"** — three-step
  checklist before importing any submodule file: (1) grep for auth env-var
  reads; (2) trace outbound HTTP; (3) trace subprocess spawns.
- **§9.4** — cross-reference §9.6 and PRD §7.2.5.
- **§7** — note that A3 will add two more submodules, still unused in Phase 0.

## Exit criteria

- [ ] All above sections revised.
- [ ] SESSION-START internally consistent with PRD v0.5.
- [ ] Diff proposed for review before commit.
- [ ] Commit `docs(session-start): aggregator strategy + auth-chain rule (#NN)` merged.

## {DEPENDS:A1}

## Refs

- Root epic: #3
""",
    },
    {
        "key": "A3",
        "title": "chore: vendor claude-mem and headroom as submodules",
        "labels": ["copilotmem", "type-chore", "area-infra", "phase-0", "priority-p1"],
        "area": "Infra", "priority": "P1", "type": "Chore", "phase": "Phase 0",
        "depends_on": ["A2"],
        "body": """## Purpose

Add `vendor/claude-mem/` and `vendor/headroom/` as git submodules, per PRD
v0.5 §7.2 (landed in A1). Unused in Phase 0 code but needs to be in place so
Phase 1/2 issues can reference stable paths.

## Steps

1. `git submodule add https://github.com/prajoria/claude-mem.git vendor/claude-mem`
2. `git submodule add https://github.com/prajoria/headroom.git vendor/headroom`
3. Update `CLAUDE.md` "Vendored upstream" section to list all three submodules.
4. Update `SESSION-START.md` §3 verification block: expected submodule count = 3.
5. Verify `git submodule status` shows three entries locally.
6. Verify a fresh clone with `git submodule update --init --recursive` populates all three.

## Exit criteria

- [ ] Two `git submodule add` commands executed; commit `chore: vendor claude-mem and headroom as submodules (#NN)` merged.
- [ ] `git submodule status` shows exactly 3 entries.
- [ ] `CLAUDE.md` and `SESSION-START.md` §3 updated in the same or a follow-up commit.
- [ ] Freshly-cloned test verifies submodule init works.

## {DEPENDS:A2}

## Refs

- Root epic: #3
""",
    },

    # -------- Phase B: Phase 0 code slices --------
    {
        "key": "B1",
        "title": "feat(infra): project foundations — package.json, tsconfig, bunfig, CI",
        "labels": ["copilotmem", "type-feature", "area-infra", "phase-0", "priority-p0"],
        "area": "Infra", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["A3"],
        "body": """## Purpose

Land the minimum project skeleton so everything else has something to build against.

## Files to create

- `package.json` — Bun runtime; pin Hono 4.x, TypeScript 5.x, `@types/node`, minimal dev deps.
- `tsconfig.json` — strict, ESM, NodeNext resolution.
- `bunfig.toml` — reproducible test/install settings.
- `config.example.toml` — documented default configuration file.
- `.prettierrc`, `.editorconfig` — style baselines.
- `.github/workflows/ci.yml` — runs `bun install && bun run typecheck && bun test` on Ubuntu AND Windows runners. Windows-first per PRD §6.

## Exit criteria

- [ ] `bun install && bun run typecheck` succeeds on empty `src/` locally.
- [ ] CI green on both Ubuntu and Windows runners.

## {DEPENDS:A3}

## Refs

- Root epic: #3
- PRD §10.1 (Bun runtime), §10.2 (Hono)
""",
    },
    {
        "key": "B2",
        "title": "feat(shared): shared utilities — paths, config, logger, pidfile",
        "labels": ["copilotmem", "type-feature", "area-shared", "phase-0", "priority-p0"],
        "area": "Shared", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B1"],
        "body": """## Purpose

Everything else imports these; land them first.

## Files

- `src/shared/paths.ts` — encodes PRD §7.5 namespace table (%LOCALAPPDATA%\\\\copilotmem\\\\ on Windows, ~/.local/share/copilotmem/ on Unix).
- `src/shared/config.ts` — TOML + `COPILOTMEM_*` env + CLI-arg merge.
- `src/shared/logger.ts` — JSONL, one file per day in `<state>/logs/`, request-ID propagation.
- `src/shared/pidfile.ts` — atomic write-rename, stale-PID cleanup, `--force` semantics per PRD §13 and SESSION-START §9.1.
- Unit tests per module, must pass on Windows AND Linux CI.

## Exit criteria

- [ ] All modules implemented + unit-tested.
- [ ] Windows CI green.

## {DEPENDS:B1}

## Refs

- Root epic: #3
- PRD §7.5 (namespace), §13 (pidfile mitigation)
""",
    },
    {
        "key": "B3",
        "title": "feat(pipeline): define RequestContext / ResponseContext / ProxyExtension types",
        "labels": ["copilotmem", "type-feature", "area-pipeline", "phase-0", "priority-p1"],
        "area": "Pipeline", "priority": "P1", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B1"],
        "body": """## Purpose

Types only — no loader/executor. Runtime (B6) follows once vanilla core is proven.
A stub identity extension should typecheck against the interface.

## Files

- `src/pipeline/types.ts` — `RequestContext`, `ResponseContext`, `ProxyExtension` interfaces per PRD §8.3.

## Exit criteria

- [ ] Types compile.
- [ ] Stub identity extension typechecks against the interface.

## {DEPENDS:B1}

## Refs

- Root epic: #3
- PRD §8.3 (extension contract)
""",
    },
    {
        "key": "B4a",
        "title": "test(contract): vanilla-invariant harness (record + replay)",
        "labels": ["copilotmem", "type-feature", "area-tests", "phase-0", "priority-p0"],
        "area": "Tests", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B2", "B3"],
        "body": """## Purpose

The vanilla-invariant test from PRD §12 lands BEFORE any core code so it can catch
drift from day one. This is the single most important test in the whole project.

## Files

- `tests/contract/record-fixtures.ts` — records N request/response pairs by hitting
  the `vendor/copilot-api/` submodule directly. Requires a real Copilot token, so gated
  behind an env var; CI skips recording, only replays.
- `tests/contract/vanilla-invariant.test.ts` — replays fixtures through CopilotMem in
  `--vanilla` mode; asserts byte-identical responses.
- `tests/fixtures/.gitkeep` — fixtures directory. Fixtures themselves are gitignored
  (may contain PII from real prompts); local-only.

## Exit criteria

- [ ] Harness is wired.
- [ ] Tests exist and skip cleanly when no fixtures present (not failed).
- [ ] Recording flow documented in `tests/contract/README.md`.

## {DEPENDS:B2,B3}

## Refs

- Root epic: #3
- PRD §12 ("Contract-test corpus of 200 recorded requests")
""",
    },
    {
        "key": "B4b",
        "title": "test(contract): no-second-auth grep-based enforcement",
        "labels": ["copilotmem", "type-feature", "area-tests", "area-governance", "phase-0", "priority-p0"],
        "area": "Tests", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B1"],
        "body": """## Purpose

Enforces PRD §7.2.5 (landed in A1) — the single-auth-chain rule — via grep-based
contract test that runs on every commit. Lands BEFORE any submodule import can violate it.

## Forbidden strings (initial list; extend as discovered)

- Env vars: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_MEM_ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`
- Function names: `buildIsolatedEnvWithFreshOAuth`, `readClaudeOAuthToken`, `getAuthMethodDescription`
- Hostnames: `api.anthropic.com`, `console.anthropic.com`, `claude.ai/api`

## Forbidden imports

- `vendor/claude-mem/src/shared/EnvManager*`
- `vendor/claude-mem/src/services/worker/ClaudeProvider*`
- `vendor/claude-mem/src/services/worker/knowledge/KnowledgeAgent*`
- `vendor/claude-mem/src/cli/*`
- `vendor/claude-mem/src/hooks/*`
- `vendor/claude-mem/src/npx-cli/*`
- `vendor/claude-mem/src/server/runtime/create-server-service*`

## Files

- `tests/contract/no-second-auth.test.ts` — scans `src/**/*.{ts,tsx}` for forbidden strings + imports.

## Exit criteria

- [ ] Test passes on the empty `src/` tree (no false positives).
- [ ] Test fails if a forbidden string is planted anywhere under `src/`.
- [ ] CI runs it on every commit.

## {DEPENDS:B1}

## Refs

- Root epic: #3
- PRD §7.2.5, §5.2 (single-auth-chain rule)
- SESSION-START §9.4, §9.6 (auth-chain trap + audit checklist)
""",
    },
    {
        "key": "B5",
        "title": "feat(core): core proxy — routes, translation, upstream, auth, TOS rate-limit",
        "labels": ["copilotmem", "type-feature", "area-core", "phase-0", "priority-p0"],
        "area": "Core", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B4a", "B4b"],
        "body": """## Purpose

Thin adapters over `vendor/copilot-api/` implementing the 8 endpoints of PRD §5.1.
Both contract tests (B4a vanilla-invariant, B4b no-second-auth) must be green
before merging.

## Files

- `src/core/proxy.ts` — Hono app, binds `127.0.0.1:4242` by default.
- `src/core/routes/` — Hono handlers for `/v1/chat/completions`, `/v1/messages`, `/v1/messages/count_tokens`, `/v1/embeddings`, `/v1/models`, `/v1/usage`, `/token`, `/health`.
- `src/core/translation/` — thin adapters over `vendor/copilot-api/src/routes/messages/{non-stream,stream}-translation.ts`.
- `src/core/upstream/` — thin adapters over `vendor/copilot-api/src/services/copilot/*`.
- `src/core/auth/` — thin adapter over `vendor/copilot-api/src/services/github/*` device-code flow.
- `src/core/rate-limit.ts` — TOS-compliance limiter (core, not toggleable per PRD §10.9).

## Exit criteria

- [ ] Fixtures record via B4a's harness against real Copilot upstream.
- [ ] B4a vanilla-invariant replay passes byte-identically.
- [ ] B4b no-second-auth passes.
- [ ] `curl http://127.0.0.1:4242/health` returns 200.

## {DEPENDS:B4a,B4b}

## Refs

- Root epic: #3
- PRD §5.1 (core endpoints), §10.9 (TOS rate-limit is core)
""",
    },
    {
        "key": "B6",
        "title": "feat(pipeline): runtime — isolation, loader, executor",
        "labels": ["copilotmem", "type-feature", "area-pipeline", "phase-0", "priority-p0"],
        "area": "Pipeline", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B5"],
        "body": """## Purpose

The middleware machinery. Wired into `src/core/proxy.ts`, empty extension list =
same behavior as B5.

## Files

- `src/pipeline/isolation.ts` — try/catch + timeout wrapper enforcing fail-open (PRD §2).
- `src/pipeline/loader.ts` — dynamic-imports `src/extensions/*/extension.ts`; failed
  loads warn + mark unavailable + continue startup.
- `src/pipeline/executor.ts` — runs the 9 stages in PRD §8.1 order; core stages non-skippable.

## Exit criteria

- [ ] B4a contract test still passes with executor in-path, zero extensions loaded.
- [ ] Chaos test placeholder in `tests/unit/pipeline-isolation.test.ts` (full impl in B8).

## {DEPENDS:B5}

## Refs

- Root epic: #3
- PRD §8.1 (pipeline stages), §2 (fail-open invariant)
""",
    },
    {
        "key": "B7",
        "title": "feat(cli): serve / auth / status / config / doctor-stub",
        "labels": ["copilotmem", "type-feature", "area-cli", "phase-0", "priority-p0"],
        "area": "CLI", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B6"],
        "body": """## Purpose

User-facing CLI wrapping the proxy + auth flows. `doctor` is a stub in Phase 0;
full impl in Phase 3.

## Files

- `src/cli/index.ts` — subcommand dispatcher.
- `src/cli/serve.ts` — `--port`, `--extensions`, `--vanilla`, `--config`, `--bind`, `--force`. Pidfile-based startup handshake (SESSION-START §9.1). Never spawns subprocesses with output silenced (§9.2).
- `src/cli/auth.ts` — GitHub Copilot device-code flow (wraps submodule).
- `src/cli/status.ts` — reads pidfile, hits `/health`, shows loaded extensions.
- `src/cli/config.ts` — get/set config values.
- `src/cli/doctor.ts` — Phase 0 stub; prints "not yet implemented — see Phase 3".

## Exit criteria

- [ ] `bun run src/cli/index.ts serve --vanilla` starts.
- [ ] `curl http://127.0.0.1:4242/health` returns 200.
- [ ] Pidfile prevents second `serve` from starting without `--force`.

## {DEPENDS:B6}

## Refs

- Root epic: #3
- PRD §9.2 (CLI surface)
- SESSION-START §9.1 (pidfile), §9.2 (no silent daemons)
""",
    },
    {
        "key": "B8",
        "title": "test: isolation + coexistence + concurrency",
        "labels": ["copilotmem", "type-feature", "area-tests", "phase-0", "priority-p0"],
        "area": "Tests", "priority": "P0", "type": "Feature", "phase": "Phase 0",
        "depends_on": ["B7"],
        "body": """## Purpose

The rest of PRD §12's success criteria that aren't covered by B4a/B4b.

## Files

- `tests/unit/pipeline-isolation.test.ts` — chaos test: always-throws extension
  does not break request flow ("Failure isolation holds" per §12).
- `tests/coexistence/three-way.test.ts` — mock copilot-api on :4141 + mock
  claude-mem worker on :37777 + real CopilotMem on :4242 with zero collision
  (PRD §7.5 required test).
- Concurrent-session load test per PRD §14 Phase 0 ("Verify concurrent-session
  behavior with a load test").

## Exit criteria

- [ ] All §12 success criteria measurable for v0.1.
- [ ] All tests green on Ubuntu and Windows CI.

## {DEPENDS:B7}

## Refs

- Root epic: #3
- PRD §12 (success criteria), §7.5 (coexistence test), §14 (Phase 0 load test)
""",
    },
    {
        "key": "B9",
        "title": "docs+release: ARCHITECTURE.md, install.ps1, v0.1 tag",
        "labels": ["copilotmem", "type-task", "area-docs", "phase-0", "priority-p1"],
        "area": "Docs", "priority": "P1", "type": "Task", "phase": "Phase 0",
        "depends_on": ["B7", "B8"],
        "body": """## Purpose

Phase 0 closeout — docs, Windows installer, single-binary smoke test, v0.1 tag.

## Files / actions

- `docs/ARCHITECTURE.md` — concretizes PRD §8 with class/module design and
  sequence diagrams for concurrent-session request flow.
- `scripts/install.ps1` — Windows bootstrap.
- `bun build --compile` produces single binary; smoke-tested on Windows.
- Tag `v0.1` per PRD §14.

## Exit criteria

- [ ] Docs published.
- [ ] Windows install script runs on a fresh VM.
- [ ] Compiled binary passes B4a contract test.
- [ ] `v0.1` tag pushed.

## {DEPENDS:B7,B8}

## Refs

- Root epic: #3
- PRD §14 (Phase 0 exit → v0.1)
""",
    },
]


# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------

def run(cmd: list[str], capture: bool = True, check: bool = True) -> str:
    """Run a subprocess command, return stdout."""
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=False,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        print(f"[error] command failed: {' '.join(cmd)}", file=sys.stderr)
        print(f"[error] stderr: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def load_project_ids() -> dict:
    if not PROJECT_JSON.exists():
        print(f"[error] {PROJECT_JSON} not found — run project setup first (#2).", file=sys.stderr)
        sys.exit(1)
    return json.loads(PROJECT_JSON.read_text(encoding="utf-8"))


def topo_sort(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return batch in topological order so dependencies exist before dependents."""
    by_key = {i["key"]: i for i in batch}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(key: str, stack: set[str]) -> None:
        if key in seen:
            return
        if key in stack:
            raise ValueError(f"cycle detected involving {key}")
        stack.add(key)
        for dep in by_key[key].get("depends_on", []):
            if dep not in by_key:
                raise ValueError(f"{key} depends on unknown key {dep}")
            visit(dep, stack)
        stack.remove(key)
        seen.add(key)
        ordered.append(by_key[key])

    for issue in batch:
        visit(issue["key"], set())
    return ordered


def check_no_existing_titles(titles: list[str]) -> None:
    """Refuse to run live if any target title already exists as an open issue."""
    out = run(["gh", "issue", "list", "--repo", REPO, "--state", "open", "--limit", "200", "--json", "title"])
    existing = {i["title"] for i in json.loads(out)}
    collisions = [t for t in titles if t in existing]
    if collisions:
        print("[error] the following titles already exist as open issues:", file=sys.stderr)
        for c in collisions:
            print(f"  - {c}", file=sys.stderr)
        print("[error] refusing to double-file. Close or rename the existing issues, then retry.", file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def dry_run(ordered: list[dict[str, Any]]) -> None:
    print(f"[dry-run] would file {len(ordered)} issues on {REPO}")
    print(f"[dry-run] topological order (dependencies first):")
    print()
    for idx, i in enumerate(ordered, start=1):
        deps = ", ".join(i.get("depends_on", [])) or "(none)"
        labels = ", ".join(i["labels"])
        print(f"  {idx:2d}. [{i['key']:4s}] {i['title']}")
        print(f"        labels: {labels}")
        print(f"        fields: Area={i['area']}, Priority={i['priority']}, Type={i['type']}, Phase={i['phase']}")
        print(f"        depends_on (local keys): {deps}")
        print(f"        body length: {len(i['body'])} chars")
        print()


def live_run(ordered: list[dict[str, Any]], project: dict) -> None:
    proj_id = project["project"]["id"]
    fields = project["fields"]

    # Pass 1: file each issue in topological order, record real numbers.
    key_to_num: dict[str, int] = {}
    key_to_nodeid: dict[str, str] = {}

    print(f"[live] Pass 1 — filing {len(ordered)} issues in dependency order...")
    for i in ordered:
        # Resolve depends_on placeholder in body to a preliminary form
        # (will be re-edited in Pass 2 with real numbers).
        body = i["body"].replace(
            f"{{DEPENDS:{','.join(i.get('depends_on', []))}}}",
            f"Depends on: {', '.join(i.get('depends_on', []))} (local keys; real #s wired in Pass 2)"
            if i.get("depends_on") else ""
        )
        args = ["gh", "issue", "create", "--repo", REPO,
                "--title", i["title"],
                "--body", body,
                "--label", ",".join(i["labels"]),
                "--assignee", "@me"]
        url = run(args).strip()
        # URL is like https://github.com/prajoria/copilotmem/issues/NN
        num = int(url.rsplit("/", 1)[1])
        key_to_num[i["key"]] = num

        # Fetch node_id
        node_id = json.loads(run(["gh", "issue", "view", str(num), "--repo", REPO, "--json", "id"]))["id"]
        key_to_nodeid[i["key"]] = node_id
        print(f"  [{i['key']:4s}] #{num}  {i['title'][:60]}")

    # Pass 2: fix up Depends-on lines with real issue numbers.
    print(f"[live] Pass 2 — rewriting Depends-on lines with real issue numbers...")
    for i in ordered:
        deps = i.get("depends_on", [])
        if not deps:
            continue
        placeholder = f"Depends on: {', '.join(deps)} (local keys; real #s wired in Pass 2)"
        replacement = "Depends on " + ", ".join(f"#{key_to_num[k]}" for k in deps)
        num = key_to_num[i["key"]]

        current_body = json.loads(run(["gh", "issue", "view", str(num), "--repo", REPO, "--json", "body"]))["body"]
        new_body = current_body.replace(placeholder, replacement)
        run(["gh", "issue", "edit", str(num), "--repo", REPO, "--body", new_body])
        print(f"  #{num}: wired {len(deps)} dependency reference(s)")

    # Pass 3: attach each issue to project #6 and set fields.
    print(f"[live] Pass 3 — attaching to project #{project['project']['number']} + setting fields...")
    for i in ordered:
        node_id = key_to_nodeid[i["key"]]
        item_id = json.loads(run([
            "gh", "api", "graphql",
            "-f", 'query=mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}',
            "-f", f"p={proj_id}",
            "-f", f"c={node_id}",
        ]))["data"]["addProjectV2ItemById"]["item"]["id"]

        for field_name, value in [("Area", i["area"]), ("Priority", i["priority"]),
                                   ("Type", i["type"]), ("Phase", i["phase"])]:
            field_id = fields[field_name]["id"]
            option_id = fields[field_name]["options"][value]
            run([
                "gh", "api", "graphql",
                "-f", 'query=mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$o}}){projectV2Item{id}}}',
                "-f", f"p={proj_id}",
                "-f", f"i={item_id}",
                "-f", f"f={field_id}",
                "-f", f"o={option_id}",
            ])
        print(f"  #{key_to_num[i['key']]}: attached, fields set")

    print()
    print(f"[live] DONE. Filed issues:")
    for i in ordered:
        print(f"  #{key_to_num[i['key']]}  {i['key']:4s}  {i['title']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-file Phase A/B issues on prajoria/copilotmem.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no API calls")
    parser.add_argument("--live", action="store_true", help="Actually file the issues")
    args = parser.parse_args()

    if not (args.dry_run or args.live):
        parser.print_help()
        sys.exit(1)

    ordered = topo_sort(BATCH)

    if args.dry_run:
        dry_run(ordered)
        return

    project = load_project_ids()
    check_no_existing_titles([i["title"] for i in ordered])
    live_run(ordered, project)


if __name__ == "__main__":
    main()
