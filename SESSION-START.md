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
# Expected: <sha> vendor/copilot-api (v0.7.0-<n>-g<sha>)
# Submodule URL should be https://github.com/prajoria/copilot-api.git

# 3. Repository owner identity
git config user.name           # Expected: Prashant Rajoria
git config user.email          # Expected: prashant.rajoria@gmail.com
```

If the submodule directory (`vendor/copilot-api/`) is empty after a fresh clone, run:

```bash
git submodule update --init --recursive
```

---

## 4. The submodule strategy (critical to understand)

CopilotMem uses a **hybrid** approach for its three source projects. This is not a common pattern; misunderstanding it will produce wrong architectural decisions.

| Source project | Strategy | Location | Why |
|---|---|---|---|
| [`prajoria/copilot-api`](https://github.com/prajoria/copilot-api) | **Git submodule** | `vendor/copilot-api/` | Same language (TypeScript), small (~2500 LOC), stable, well-scoped protocol translation. Cheap upstream sync. |
| [`thedotmack/claude-mem`](https://github.com/thedotmack/claude-mem) | **Ported / rewritten** | Will live in `src/extensions/memory/` | Wrong shape (Claude Code IDE plugin), 30k LOC of unwanted surface (Chroma vector store, React viewer, PostgreSQL server mode, multi-host installers). |
| [`prajoria/headroom`](https://github.com/prajoria/headroom) | **Ported / rewritten** | Will live in `src/extensions/compress/` | Wrong language (Python 76.8% + Rust 18.4%). Would force a Python+Rust toolchain into every build. |

**Only copilot-api is a submodule.** The other two are reimplementations in TypeScript with attribution headers referencing the upstream commit SHA they were derived from. This is documented in `docs/PRD.md` §7.2.

**The submodule URL points at Prashant's own fork** (`prajoria/copilot-api`), not upstream `ericc-ch/copilot-api`. The developer's daily working copy of the fork lives at `H:\masterswork\git\OpenBBTechnical\copilot-api\` — same remote, so the submodule and the working copy naturally stay in sync when the developer bumps the SHA.

---

## 5. Non-negotiable design invariants

These come directly from PRD §2 and §4. Any code you write must respect them.

1. **The vanilla proxy contract is inviolable.** With all extensions disabled or crashing, CopilotMem must forward requests to Copilot with byte-identical results to a bare proxy. Contract tests will enforce this. Any extension that can degrade the base path is a bug.
2. **Extensions fail open.** Each extension runs inside a try/catch boundary. Extension crashes get logged and the affected extension is skipped for that request; the request still succeeds via the remaining pipeline.
3. **Local-first storage.** No hosted services, no cloud calls except to the configured upstream. All state lives under the CopilotMem state directory (see §7.5 of the PRD).
4. **Single runtime, single database.** One Bun process. One SQLite file. External deps like Python (for optional prose compression) are opt-in only.
5. **Windows tested first.** File-locking, atomic writes, encoding assumptions that hold on Unix but break on Windows are a known category of bug. All features need Windows CI to pass.

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
| Process title | `copilotmem serve` |
| Plugin/marketplace cache | **NONE** — CopilotMem is not a plugin |

**Coexistence test** (must pass before v0.1 ships): copilot-api on `:4141`, claude-mem's worker on `:37777`, and CopilotMem on `:4242` all running simultaneously on the same machine, with no collision.

---

## 7. Phase 0 work items (what to build next)

The repo currently has: PRD, README, LICENSE, .gitignore, .gitmodules, `vendor/copilot-api/` submodule. **Nothing else.**

Phase 0 requires:

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
- Do **not** vendor claude-mem or headroom source into this repo. They are ports, not imports. Copy the algorithmic ideas with attribution headers, don't paste files.
- Do **not** introduce a build step that requires Python or Rust at install time. Optional prose compression uses a lazy Python sidecar; that's the only exception, and it must be opt-in.
- Do **not** commit any file to `<state>/` or reference absolute paths that leak the developer's machine layout.

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

### 9.5 Multiple-version confusion

The claude-mem plugin had two versions installed side-by-side (`13.10.2` and `13.10.3`), and hooks race-picked between them, causing port collisions. **Mitigation in CopilotMem**:

- Single binary. There is exactly one version installed at a time. No plugin manager to leave stale versions.

---

## 10. Runtime and dependencies

**Confirmed working combinations** (from the source-project analysis):

- **Bun 1.3+** — primary runtime. Ships `bun:sqlite` natively.
- **Node.js 20.12+** — compatibility target; tests must pass on Node too.
- **TypeScript 5.x** — strict mode.
- **Hono 4.x** — HTTP framework. Runs on both Bun and Node.
- **tree-sitter** (for Phase 2 code compression) — Bun has native bindings.
- **Windows 11, macOS 14+, Linux (glibc 2.31+ or musl)** — supported platforms.

**No cloud dependencies at build or runtime.**

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
