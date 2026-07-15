# SESSION-START — CopilotMem project kickoff

**Purpose**: Everything a fresh Claude Code session needs to pick up work on CopilotMem cold, without reading the transcript that produced this project.

**How to use this file**: If you're a new Claude Code session opened at `H:\masterswork\git\copilotmem\`, read this file **before doing anything else**. It supersedes any assumptions from other CLAUDE.md files up the directory tree.

---

## 1. What CopilotMem is

CopilotMem is a self-hosted local HTTP proxy for AI coding assistants. It:

- Sits between the developer's tools (Claude Code, Copilot CLI, Cursor, Codex, curl, custom scripts) and their upstream LLM provider (GitHub Copilot at launch).
- Presents both OpenAI and Anthropic API surfaces on the client side.
- Adds two opt-in middleware capabilities on top of vanilla proxying: **persistent cross-session memory** and **prompt compression**.
- Guarantees a working vanilla pass-through path — extensions can be disabled or fail without breaking basic proxying.
- Consolidates three previously-separate open-source efforts into one binary.

**Full product definition**: [`docs/PRD.md`](docs/PRD.md) — v0.4. Read this before touching any code. It is the authoritative source for scope, architecture, design decisions, and non-goals.

**Scope constraints** (from PRD §3):

- **Single user, single workstation, multiple concurrent sessions.** No team features, no multi-tenant, no hosted mode, no API-key auth.
- **Windows is first-tested platform** — every feature must have a passing Windows test run before it's considered done.
- **Localhost-only bind by default.** No cloud, no remote access unless explicitly opted into via `--bind`.

---

## 2. Where we are in the roadmap

The PRD (§14) defines four phases. Current status:

| Phase | Deliverable | Status |
|---|---|---|
| **Phase 0** | Byte-identical vanilla drop-in for the imported Copilot proxy code; empty extension pipeline | **In progress** — repo bootstrapped, submodule vendored, scaffold not yet written |
| Phase 1 | Memory extension with capture, search, viewer, and claude-mem migration | Not started |
| Phase 2 | Compression extension with SmartCrusher, CodeCompressor, CCR, CacheAligner | Not started |
| Phase 3 | Polish & portability: `export-state`, `import-state`, `doctor`, Windows installer, docs walkthrough | Not started |

**You (the fresh session) will be working in Phase 0.** Specifically:

- The repo has been initialized on `main` with the PRD, README, LICENSE, and .gitignore (commit `19b120b`).
- A feature branch `feat/phase-0-scaffold` is checked out with two additional commits: the submodule addition and its URL retarget.
- The next work items are documented in §7 of this file.

---

## 3. Repository state — verify this first

Run these three commands and confirm output matches. If anything diverges, stop and investigate before making changes.

```bash
# 1. Current branch and log
git branch --show-current      # Expected: feat/phase-0-scaffold
git log --oneline --all
# Expected:
#   761e0d5 chore: point copilot-api submodule at prajoria/copilot-api
#   69294b5 chore: vendor copilot-api as submodule
#   19b120b chore: initial repository bootstrap

# 2. Submodule state
git submodule status
# Expected (after A3 = #9 landed): THREE entries
#   <sha> vendor/claude-mem (heads/main)
#   <sha> vendor/copilot-api (v0.7.0-<n>-g<sha>)
#   <sha> vendor/headroom (heads/main)
# All three URLs should be under github.com/prajoria/*

# 3. Repository owner identity
git config user.name           # Expected: Prashant Rajoria
git config user.email          # Expected: prashant.rajoria@gmail.com

# 4. Commit-msg hook installed (issue-first workflow — see §8.5)
git config core.hooksPath      # Expected: .githooks
# If empty, run: ./scripts/install-hooks.sh  (or .ps1 on Windows)
```

If the submodule directory (`vendor/copilot-api/`) is empty after a fresh clone, run:

```bash
git submodule update --init --recursive
```

---

## 4. The submodule strategy (critical to understand)

CopilotMem uses a **uniform three-submodule aggregator model** for its source projects. All three live under `vendor/`; language decides integration mode. This replaces the earlier "hybrid: one submodule + two ports" plan (see PRD §7.2 v0.5 changelog for rationale).

| Source project | Location | Integration mode | Auth-surface handling |
|---|---|---|---|
| [`prajoria/copilot-api`](https://github.com/prajoria/copilot-api) | `vendor/copilot-api/` | **In-process** (ESM import) | Its GitHub Copilot device-code flow **is** CopilotMem's single sanctioned auth chain. Imported as-is. |
| [`prajoria/claude-mem`](https://github.com/prajoria/claude-mem) (forked from `thedotmack/claude-mem`) | `vendor/claude-mem/` | **In-process, SELECTIVE** (ESM import per PRD §7.2.2 allowlist) | Denylist blocks `EnvManager`, `ClaudeProvider`, `KnowledgeAgent`, plugin CLI/hooks/npx surfaces. Summarizer replaced by `src/extensions/memory/summarizer.ts` shim. |
| [`prajoria/headroom`](https://github.com/prajoria/headroom) | `vendor/headroom/` | **Supervised subprocess** (UDS on Linux/macOS; Named Pipe on Windows) | Launched in a config that disables hosted-inference/telemetry. No LLM calls in the compression path. Audited before enabling per §9.6. |

**All three are your forks under `prajoria/`.** This means bug fixes flow via `H:\masterswork\git\OpenBBTechnical\copilot-api\` (and equivalent working clones) → push → `git submodule update` in this repo. Never edit `vendor/*/` in-place from CopilotMem.

**Do not import from a submodule without an audit.** Every file imported from `vendor/claude-mem/` or `vendor/headroom/` must pass the three-step auth-chain audit in §9.6 first. Grep-based contract test `tests/contract/no-second-auth.test.ts` (landing in issue #14) enforces this on every commit.

**Change from earlier revisions**: Sessions predating #7 (PRD v0.5) may have been briefed on a plan that called claude-mem and headroom "ported / rewritten in TypeScript" — that plan is superseded. If you find a CLAUDE.md, SESSION-START, or PRD reference implying a port for those two, treat it as stale and either edit or file an issue.

---

## 5. Non-negotiable design invariants

These come directly from PRD §2, §4, and §7.2.5. Any code you write must respect them.

1. **The vanilla proxy contract is inviolable.** With all extensions disabled or crashing, CopilotMem must forward requests to Copilot with byte-identical results to a bare proxy. Contract tests will enforce this. Any extension that can degrade the base path is a bug.
2. **Extensions fail open.** Each extension runs inside a try/catch boundary. Extension crashes get logged and the affected extension is skipped for that request; the request still succeeds via the remaining pipeline.
3. **Single-auth-chain rule** (PRD §7.2.5). No caller of any CopilotMem component may require a Claude/Anthropic OAuth login separate from the Copilot upstream token CopilotMem already holds. Every internal LLM call routes through `http://127.0.0.1:4242` with `X-CopilotMem-Extensions: none` as recursion guard. Enforced by `tests/contract/no-second-auth.test.ts` + per-vendored-file audit (§9.6). **This is what makes CopilotMem architecturally different from a naive tool aggregator; losing it collapses the product's value.**
4. **Local-first storage.** No hosted services, no cloud calls except to the configured upstream. All state lives under the CopilotMem state directory (see §7.5 of the PRD).
5. **Single install bundle** (PRD §10.5 v0.5). One CopilotMem binary + one pre-built headroom sidecar + submodule copies = one download for the user. Internally three projects; externally one bundle.
6. **Windows tested first.** File-locking, atomic writes, encoding assumptions that hold on Unix but break on Windows are a known category of bug. All features need Windows CI to pass.

---

## 6. Namespace separation — DO NOT reuse existing paths or ports

CopilotMem must coexist with the developer's existing tools during migration. Everything CopilotMem touches must be namespaced differently from `copilot-api` (existing proxy on `:4141`) and `claude-mem` (memory plugin using `~/.claude-mem/`).

**Definitive mapping (from PRD §7.5)**:

| Resource | CopilotMem uses |
|---|---|
| HTTP port | **`4242`** (never `4141`, never `37777`) |
| State directory (Windows) | `%LOCALAPPDATA%\copilotmem\` |
| State directory (Unix) | `~/.local/share/copilotmem/` |
| SQLite database | `<state>/copilotmem.db` |
| PID file | `<state>/copilotmem.pid` |
| Log directory | `<state>/logs/` |
| Upstream token file | `<state>/upstream_token` (not `github_token`) |
| Config file | `<state>/config.toml` |
| Environment variable prefix | `COPILOTMEM_*` |
| Placeholder API key value | `copilotmem-proxy` |
| Process title (main) | `copilotmem serve` |
| Plugin/marketplace cache | **NONE** — CopilotMem is not a plugin |
| **Headroom sidecar IPC socket** (v0.5) | `<state>/services/headroom/sock` (UDS on Linux/macOS); `\\.\pipe\copilotmem-headroom` (Named Pipe on Windows) |
| **Headroom sidecar PID / logs** (v0.5) | `<state>/services/headroom/{pid,logs/}` |
| **Recursion-guard header** (v0.5) | `X-CopilotMem-Extensions: none` on every internal LLM call. Enforces PRD §7.2.5. |

**Coexistence test** (must pass before v0.1 ships): copilot-api on `:4141`, claude-mem's worker on `:37777`, and CopilotMem on `:4242` all running simultaneously on the same machine, with no collision.

---

## 7. Phase 0 work items (what to build next)

The repo currently has: PRD (v0.5), README, LICENSE, .gitignore, .gitmodules, `vendor/copilot-api/` submodule, CLAUDE.md, `.githooks/`, `scripts/{install-hooks.{sh,ps1},file_phase_issues.py,copilotmem_project.json}`. **Nothing else in `src/` yet.**

**Two more submodules land during Phase A** (issue #9, blocking all Phase B work):
- `vendor/claude-mem/` — TypeScript, will be selectively imported per PRD §7.2.2 allowlist
- `vendor/headroom/` — Python + Rust, will run as supervised subprocess per PRD §7.2.3

Both are present but unused in Phase 0 code (Phase 0 only wraps `vendor/copilot-api/`). After #9 closes, `git submodule status` should show three entries.

Phase 0 remaining work (issues #10-#19 filed as batch under #6):

### 7.1 Project foundations

- [ ] `package.json` — declare Bun as the runtime; pin Hono, `bun:sqlite` (built-in), TypeScript. Include only the deps we need at build time; no headroom-scale bloat.
- [ ] `tsconfig.json` — strict mode, ESM, target Node/Bun compatible.
- [ ] `bunfig.toml` — reproducible test/install settings.
- [ ] `config.example.toml` — a documented default configuration file the developer copies to `<state>/config.toml`.

### 7.2 Pipeline runtime (`src/pipeline/`)

- [ ] `types.ts` — `RequestContext`, `ResponseContext`, `ProxyExtension` interfaces (see PRD §8.3 for the shape).
- [ ] `loader.ts` — dynamically imports each `src/extensions/*/extension.ts`. Failed loads log warning, mark extension unavailable, do NOT halt startup.
- [ ] `executor.ts` — runs stages in order; wraps each stage in try/catch; on exception logs with request ID and skips the stage.
- [ ] `isolation.ts` — the try/catch + timeout wrapper reused across stages.

### 7.3 Core proxy (`src/core/`)

- [ ] `proxy.ts` — Hono app entry, binds `127.0.0.1:4242` by default.
- [ ] `routes/` — Hono route handlers for `/v1/chat/completions`, `/v1/messages`, `/v1/messages/count_tokens`, `/v1/embeddings`, `/v1/models`, `/v1/usage`, `/token`, `/health`.
- [ ] `translation/` — adapters that call into `vendor/copilot-api/src/routes/messages/non-stream-translation.ts` and `stream-translation.ts`.
- [ ] `upstream/` — adapters that call into `vendor/copilot-api/src/services/copilot/*`.
- [ ] `auth/` — adapter over `vendor/copilot-api/src/services/github/*` for the device-code flow.
- [ ] TOS-compliance rate limiter (part of core per PRD §5.1 / §10.9 — not toggleable off).

### 7.4 Shared utilities (`src/shared/`)

- [ ] `config.ts` — TOML parser, env-var override merge, CLI-arg override merge.
- [ ] `paths.ts` — resolves the state directory per §7.5 of the PRD (Windows `%LOCALAPPDATA%` vs Unix `~/.local/share`), token file, log directory, PID file, database path.
- [ ] `logger.ts` — JSONL structured logging with request-ID propagation, one file per day in `<state>/logs/`.
- [ ] `pidfile.ts` — atomic write, startup handshake for port-collision detection (learned the hard way from the debugging session — see §9 below).

### 7.5 CLI (`src/cli/`)

- [ ] `index.ts` — subcommand dispatcher.
- [ ] `serve.ts` — main entry: parse `--port`, `--extensions`, `--vanilla`, `--config`, `--bind`, `--force`.
- [ ] `auth.ts` — GitHub Copilot device-code flow (wraps the submodule).
- [ ] `status.ts` — reads pidfile, hits `/health`, shows extensions loaded.
- [ ] `config.ts` — get/set config values.
- [ ] `doctor.ts` — diagnostic report for issue reporting.

### 7.6 Tests (`tests/`)

- [ ] `contract/vanilla-invariant.test.ts` — the byte-identical check. Record a corpus of requests against the submodule directly; replay them through CopilotMem in `--vanilla` mode; assert equality. This is the single most important test in the whole project (see PRD §12).
- [ ] `coexistence/three-way.test.ts` — CopilotMem on `:4242` while a mock "copilot-api on `:4141`" and mock "claude-mem worker on `:37777`" are also running. Assert zero interaction between them.
- [ ] `unit/pipeline-isolation.test.ts` — chaos test: extension that always throws does not break request flow.

### 7.7 Documentation

- [ ] `docs/ARCHITECTURE.md` — concretizes PRD §8 into class/module design with sequence diagrams for the concurrent-session request flow.
- [ ] Bootstrap script `scripts/install.ps1` for Windows.

---

## 8. How to work in this repo

### 8.1 Branch discipline

- **Feature work happens on feature branches**, one per meaningful chunk of Phase 0. The current branch `feat/phase-0-scaffold` is the umbrella for all Phase 0 work; consider breaking into sub-branches (e.g. `feat/phase-0-pipeline`, `feat/phase-0-core-routes`) if any single change gets large.
- **`main` stays clean.** Merges to `main` happen only when a whole phase is complete or when a critical fix must ship.
- **No force-pushes** to shared branches. Rewriting local feature-branch history before first push is fine.

### 8.2 Commit discipline

- Conventional Commits style: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
- Prefix with subsystem if useful: `feat(pipeline): add extension loader`.
- Body explains **why**, not just what. The initial bootstrap commits are examples of the expected level of detail.
- Never commit if pre-commit hooks or tests fail. Fix the underlying problem first.

### 8.3 Submodule discipline

- **Never edit `vendor/copilot-api/` in-place from this repo.** Those edits are in the submodule's own git, not CopilotMem's. To fix a bug in copilot-api:
  1. `cd H:/masterswork/git/OpenBBTechnical/copilot-api` (the developer's working fork clone)
  2. Make and commit the change; push to `prajoria/copilot-api`.
  3. Come back to `copilotmem/`: `cd vendor/copilot-api && git pull && cd ../..`
  4. `git add vendor/copilot-api && git commit -m "chore: bump copilot-api submodule to <sha>"`
- **Never delete `vendor/copilot-api/` and re-add** — this loses the submodule history. Use `git submodule sync`, `git submodule update`, or `git submodule set-url` instead.

### 8.4 What to NEVER do

- Do **not** add Claude Code plugin surface (`.claude-plugin/`, `hooks.json`, marketplace metadata). CopilotMem is not a plugin.
- Do **not** add lifecycle-hook integrations for any specific IDE. Capture happens at the HTTP layer.
- Do **not** add authentication surface (API keys, OAuth for callers). Single-user, localhost-only means no auth is needed by design (PRD §10.8).
- Do **not** import any file from a vendored submodule (`vendor/claude-mem/`, `vendor/headroom/`) without running the three-step auth-chain audit in §9.6 first. Any file that reads Anthropic env vars, spawns `claude` CLI, or POSTs to a non-Copilot host is **denylisted** — replace with a CopilotMem-native shim that routes through the proxy with `X-CopilotMem-Extensions: none`. This is the mechanism of PRD §7.2.5.
- Do **not** edit files inside any `vendor/*/` directory in-place from this repo. Bug fixes flow via the developer's working clone of the fork (e.g. `H:\masterswork\git\OpenBBTechnical\copilot-api\`) → push to the `prajoria/*` remote → `git submodule update` in this repo.
- Do **not** silence a child-process's stdout/stderr. The v0.5 aggregator model spawns `vendor/headroom/` as a supervised subprocess; per §9.2 all child output goes to `<state>/services/<name>/logs/`, never `/dev/null` and never a hidden Windows window.
- Do **not** commit any file to `<state>/` or reference absolute paths that leak the developer's machine layout.
- Do **not** introduce a build-time Python or Rust dependency into the **main CopilotMem process**. Those toolchains are required only for **building** `vendor/headroom/`; the CopilotMem binary itself remains Bun-only. End users of the release bundle need neither Python nor Rust.

### 8.5 Issue-first workflow (mandatory)

**No significant work happens without a tracking GitHub issue filed first.** This is the missing rung under §8.1–8.4; commits point at branches, branches point at issues, issues are what a future session reads to understand *why* a change happened.

- **"Significant work"** = anything that touches code, configuration, doc content (beyond typo fixes), the submodule set, GitHub settings (labels/milestones/repo config), CI, or the issue taxonomy itself.
- **"Tracking issue"** = an open issue in [`prajoria/copilotmem`](https://github.com/prajoria/copilotmem/issues) with a scoped title, an exit criterion, and (if dependent) a `Depends on #N` line in the body.
- **Commits, branches, and PRs cite the issue number**: `feat(pipeline): add extension loader (#12)`, branch `feat/12-extension-loader`, PR title `Add extension loader (#12)`.

**Exceptions** (allow-listed in `.githooks/commit-msg`, must stay tiny):

- `revert:` — reverting a broken commit; body cites the offending commit's issue number.
- `docs(typo):` — typo/formatting fixes in Markdown that don't change meaning.
- `docs(governance):` — the initial commit that introduced this rule and the hook itself.

Local, unstaged exploration that is discarded before any `git add` is not "work" for the rule's purposes.

**Enforcement**: `.githooks/commit-msg` rejects any commit lacking a `(#NN)` reference unless the message starts with an allow-listed prefix. Install it once per clone via `scripts/install-hooks.sh` (or `.ps1` on Windows). See §3 for the session-start check that verifies the hook is installed.

**When you spawn parallel subagents**: each agent gets exactly one issue as its scope. Claim the issue in the parent turn (assign to yourself on GitHub) before dispatching the agent. Follow-up work the agent discovers gets a *new* issue filed and linked, not silent scope expansion.

---

## 9. Lessons from the debugging session that created this project

The four-hour debugging saga that led to CopilotMem's existence produced concrete failure modes that this project must avoid. Encoding them here so the fresh session doesn't rediscover them:

### 9.1 Port collisions

The immediate trigger was multiple worker processes racing for the same port (`:37777`), each dying with EADDRINUSE, and Claude Code hooks respawning them in a loop that produced 400+ log lines in 20 minutes. **Mitigation in CopilotMem**:

- Pidfile-based startup handshake. On startup, read the pidfile, check if that PID is alive, if so exit with a clear message (not silent), if not clean the stale pidfile and proceed.
- `copilotmem serve --force` explicitly kills the previous owner via the pidfile before starting. Never silent.
- The port is `4242`, deliberately non-adjacent to any existing tool's port (see §6 above).

### 9.2 Silent daemon failures

The claude-mem worker on Windows crashed silently every startup because its `spawnDaemon` function used `PowerShell Start-Process -WindowStyle Hidden` with `stdio: 'ignore'`, discarding every error message. **Mitigation in CopilotMem**:

- Never spawn subprocesses with output silenced. Log everything to `<state>/logs/`.
- The `serve` command runs in the foreground by default. Backgrounding is opt-in via `--daemon`, and even then stdout/stderr are redirected to log files, never discarded.
- `copilotmem doctor` includes a "recent startup errors" section that surfaces any silent-daemon failure that did happen.

### 9.3 Windows-specific bugs

Several failures were Windows-only: `bun.cmd` shim missing when Bun installed via winget, `%LOCALAPPDATA%` vs `~/.local/share` convention mismatch, PowerShell 5.1 UTF-8 handling, file-locking preventing SQLite operations. **Mitigation in CopilotMem**:

- Bun ships as a single compiled binary; no `bun.cmd` shim needed.
- State directory uses `%LOCALAPPDATA%` on Windows (native convention), not `~/.local/share` (Linux XDG imported).
- All PowerShell scripts assume `pwsh` (PowerShell 7+, UTF-8 native); explicitly reject Windows PowerShell 5.1 with a clear message.
- SQLite in WAL mode. Atomic-write-then-rename for all file operations. Windows Defender exclusion documented in `docs/INSTALL.md`.

### 9.4 The "auth chain" trap

claude-mem's LLM summarizer required a completely separate Anthropic OAuth login (`/login`) from the Copilot proxy's own auth. This defeated the point of the proxy — the developer already had upstream credentials. **Mitigation in CopilotMem**:

- The memory extension's summarizer calls the CopilotMem proxy itself (with `X-CopilotMem-Extensions: none` to avoid recursion). It uses whatever upstream the proxy is already authenticated to. No separate auth chain, ever.
- **v0.5 escalation**: this became the **single-auth-chain rule** codified as PRD §7.2.5 and enforced by contract test `tests/contract/no-second-auth.test.ts` (issue #14). See §9.6 below for the pre-import audit checklist that keeps vendored submodule code from silently re-introducing this trap.

### 9.5 Multiple-version confusion

The claude-mem plugin had two versions installed side-by-side (`13.10.2` and `13.10.3`), and hooks race-picked between them, causing port collisions. **Mitigation in CopilotMem**:

- Single binary. There is exactly one version installed at a time. No plugin manager to leave stale versions.

### 9.6 Auth-chain audit for vendored code (v0.5)

When wrapping vendored submodule code (`vendor/claude-mem/`, `vendor/headroom/`), the auth-chain audit is **mandatory before any `import` statement lands** referencing that file. This is the mechanism that protects PRD §7.2.5 during ongoing development.

**Three-step checklist per vendored file, in order** (any hit blocks the import; the file must be replaced by a shim):

1. **Grep for auth-token env-var reads**. Run against the specific file (not the whole submodule):
   ```bash
   grep -nE 'ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|CLAUDE_MEM_ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN|buildIsolatedEnvWithFreshOAuth|readClaudeOAuthToken|getAuthMethodDescription' <file>
   ```
   Any hit → the file authenticates to Claude/Anthropic. Do not import; write a shim that POSTs to `http://127.0.0.1:4242` with `X-CopilotMem-Extensions: none` instead.

2. **Trace outbound HTTP for non-Copilot hosts**. Scan the file (and its transitive imports within the submodule) for hostnames other than localhost, `github.com`, or the Copilot API endpoints:
   ```bash
   grep -rnE 'api\.anthropic\.com|console\.anthropic\.com|claude\.ai/api' <file>
   ```
   Any hit → same treatment. Non-Copilot HTTP callers must be replaced.

3. **Trace subprocess spawns for CLIs that authenticate independently**. Look for `spawn`, `exec`, `execFile`, `child_process`, `Bun.spawn` calls whose command name is `claude`, `anthropic`, or a wrapper around an OAuth flow:
   ```bash
   grep -nE '(spawn|exec|execFile|Bun\.spawn)\([^)]*(claude|anthropic|/login)' <file>
   ```
   Any hit → same treatment.

**All three passes must be clean before the import is allowed.** The grep-based contract test in `tests/contract/no-second-auth.test.ts` (issue #14) is a CI backstop for what this checklist catches at development time; both layers exist because either can miss things the other catches (checklist misses newly-discovered auth surfaces; test misses whole-file semantics).

**Record the audit result** — when adding a new import from a submodule, cite the audit in the commit message body: `Auth-chain audit passed for vendor/claude-mem/src/storage/sqlite/schema.ts (no matches on any of the 3 passes).`

**When in doubt, shim.** The cost of a small shim (a few hundred lines of TypeScript that POST to the local proxy) is trivial compared to the cost of a second auth chain sneaking into the codebase. The default answer to "should I import this file?" for anything touching LLMs, spawns, or env vars is **no**.

---

## 10. Runtime and dependencies

**Main CopilotMem process (Bun-only, end-user)**:

- **Bun 1.3+** — primary runtime. Ships `bun:sqlite` natively.
- **Node.js 20.12+** — compatibility target; tests must pass on Node too.
- **TypeScript 5.x** — strict mode.
- **Hono 4.x** — HTTP framework. Runs on both Bun and Node.
- **Windows 11, macOS 14+, Linux (glibc 2.31+ or musl)** — supported platforms.

**Headroom sidecar (subprocess, `vendor/headroom/`, build-time only for developers)** — v0.5:

- **Python 3.11+** — headroom's primary language.
- **Rust toolchain (`cargo`)** — for headroom's Rust components.
- **`tree-sitter`** (for Phase 2 code compression) — headroom links this natively.
- **End users of the release bundle need neither Python nor Rust.** Each platform bundle ships the pre-built headroom binary; only contributors building headroom from source need the toolchain.

**No cloud dependencies at runtime for the main process.** The headroom sidecar is audited (§9.6) to disable hosted-inference and telemetry endpoints before it's enabled — no phone-home from any subprocess either.

---

## 11. Quick-start commands (when scaffolding lands)

Not yet functional. Placeholder for what the fresh session will build:

```bash
# Install (once package.json exists)
bun install

# Run tests
bun test

# Type-check
bun run typecheck

# Start the vanilla proxy (Phase 0 end state)
bun run src/cli/index.ts serve --vanilla
# Then: curl http://127.0.0.1:4242/health

# Once Phase 1 lands:
bun run src/cli/index.ts serve --extensions memory
```

---

## 12. Where to look for more context

- **`docs/PRD.md`** — the product's authoritative definition. Read it end-to-end at least once. Section anchors used throughout this file map to sections there.
- **`vendor/copilot-api/`** — the submodule. Its `src/` shows the protocol translation code CopilotMem will wrap. Its README explains the reverse-engineered nature of the Copilot API and the associated TOS caveats.
- **`H:\masterswork\git\OpenBBTechnical\copilot-api\`** — the developer's working fork of the same repo. Any bug in the submodule gets fixed here first, then pulled into the submodule.
- **`H:\masterswork\git\claude-mem\`** — the memory system CopilotMem is replacing. Reference for schema, query patterns, and viewer design. Do not vendor; port with attribution.
- **`H:\masterswork\git\claude-mem\docs\ai\specs\copilotmem-PRD.md`** — a mirror of `docs/PRD.md` in this project's parent workspace. Kept in claude-mem for historical reasons; treat `copilotmem/docs/PRD.md` as authoritative.

---

## 13. If you're stuck

- **Design question not answered in the PRD** → propose a change to the PRD before writing code. Do not silently make architectural decisions.
- **Something in vendor/copilot-api doesn't do what you need** → check if it needs a fix in the fork (edit at `H:\masterswork\git\OpenBBTechnical\copilot-api\`, push, bump the submodule) or if it needs to be wrapped in a `src/core/` adapter.
- **Tempted to add a new dependency** → is it required for Phase 0? Does it work on both Bun and Node? Does it work on Windows? Does it add a runtime that consumers don't already have? If any answer is no, don't add it.
- **Tempted to add a Claude Code plugin surface** → don't. Re-read §8.4.

Good luck. The design is solid; the debugging that produced it was thorough. Ship it well.
