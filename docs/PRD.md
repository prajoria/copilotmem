# CopilotMem — Product Requirements Document

**Version**: 0.5 (aggregator model + single-auth-chain rule)
**Status**: Repo bootstrapped; Phase 0 in progress
**Owner**: TBD
**Last updated**: 2026-07-14
**Scope**: Single-user, single-workstation. Multi-session and multi-project support within that scope.
**Change tracking**: Every substantive change to this repo is tracked by a GitHub issue on [`prajoria/copilotmem`](https://github.com/prajoria/copilotmem/issues) before work begins. See SESSION-START §8.5.

**v0.5 changelog** (from v0.4):
- **§7.2 rewritten** — the "hybrid submodule + port" strategy is replaced by a **uniform three-submodule aggregator model**. `claude-mem` and `headroom` become submodules under `vendor/`, joining `copilot-api`. Language mismatch (headroom's Python + Rust) is handled by running the mismatched submodule as a supervised subprocess, not by rewriting it.
- **§7.2.5 (new)** — codifies the **single-auth-chain rule** (no second Anthropic/Claude auth chain anywhere in the system). Enforced by a grep-based contract test on every commit.
- **§7.5** — namespace table adds rows for the subprocess IPC socket and the recursion-guard header value.
- **§7.3** — repo layout gains `vendor/claude-mem/` and `vendor/headroom/`; `src/extensions/{memory,compress}/` become **adapter layers** (thin wrappers + summarizer/IPC shims) rather than ports.
- **§10.5** — "single binary" reframed as **single install bundle** (Bun binary + built subprocess sidecar + submodule copies).
- **§6** — memory footprint budget adjusted for subprocess overhead (200 MB → 350 MB with default extensions enabled).
- **§12** — success criterion "First-run under 5 min" scoped to the bundled installer; other criteria unchanged.
- **§13** — recursion-loop risk elevated from High to **Critical** (breaks the single-auth-chain rule) with contract-test enforcement.
- **§14** — Phase 1 shrinks from ~3 weeks to ~1 week (wrap vs. port); Phase 2 similarly.

---

## Executive summary

CopilotMem is a local proxy for AI coding assistants, running on a single developer's workstation. It sits between the developer's tools (Claude Code, Copilot CLI, Cursor, Codex, curl, custom scripts) and their upstream LLM provider (GitHub Copilot at launch), presenting both the OpenAI and Anthropic API surfaces on the client side. In the middle, it inserts opt-in middleware for **persistent cross-session memory** and **prompt compression**. Every middleware stage can be enabled, disabled, or bypassed per-request, and the proxy always guarantees a working vanilla pass-through path.

The product consolidates three previously-separate open-source efforts — a Copilot-to-Anthropic protocol translator, a Claude-Code-specific session memory system, and a general-purpose context compression engine — into one binary with one config, one datastore, and one HTTP surface. It removes the requirement to run a specific IDE (memory captures from anything that speaks OpenAI or Anthropic), removes the requirement for a separate LLM auth chain (the memory summarizer uses the same upstream the proxy is already pointed at), and cuts operational surface from three coordinated daemons to one.

The scope is deliberately narrow: one developer, one machine, multiple concurrent coding assistant sessions across multiple projects. Team features, multi-tenant deployment, and hosted service are all non-goals.

---

## 1. Problem

Modern AI coding workflows accumulate infrastructure debt quickly. A representative single-developer setup today looks like this:

1. **A backend proxy** that presents Anthropic-compatible endpoints locally and translates them to whatever provider actually holds the developer's paid quota — commonly GitHub Copilot, since it's bundled with many developer subscriptions and covers Claude models.
2. **A memory layer** that captures prompts and observations across sessions so the assistant can reference prior work. Available implementations are typically tied to a specific host (Claude Code lifecycle hooks, Cursor rules, Codex config) and to a specific auth chain (an OAuth login separate from whatever the proxy uses).
3. **A compression layer** that shrinks prompt payloads to fit more into a request or to reduce cost. Available implementations run as separate daemons, sometimes with different runtime dependencies (Python + Rust in addition to whatever the coding assistant already needs).

Running all three concurrently on one developer's laptop produces a compounding set of problems:

- **Coordination bugs.** Each layer has its own process supervisor, port, config file, log location, and startup ordering. Failure in any one silently degrades or blocks the others.
- **Client lock-in.** Memory captured via a specific IDE's hook system is invisible to any other client. A developer who uses both Claude Code and Copilot CLI cannot share memory between them.
- **Auth sprawl.** Each layer authenticates independently. A developer proxying through GitHub Copilot may still be forced to complete an Anthropic OAuth flow so the memory summarizer works, defeating the point of the proxy.
- **Runtime bloat.** Three daemons mean three logging pipelines, three update cadences, and three chances for a dependency conflict.
- **Concurrency confusion.** When the same developer runs two or three Claude Code sessions in different project directories simultaneously, each layer needs its own answer to "which session does this event belong to." Answers rarely agree.

These are not hypothetical problems. They are the concrete failure modes observed when integrating an existing Copilot proxy, an existing Claude Code memory plugin, and an existing compression tool on a Windows workstation.

The unifying observation is that **all three tools operate at the same architectural boundary**: the HTTP call between an LLM client and an LLM endpoint. If that boundary is owned by a single proxy, all three capabilities become properties of the request path rather than separate services orbiting it. Memory becomes universal (any client wire-format is captured, regardless of the client). Compression becomes automatic (applied before the upstream call regardless of who initiated it). Auth becomes singular (the proxy has one relationship with one upstream provider). Session identity becomes centralized (all clients coordinate through the proxy's session-id header). And the operational surface reduces from three daemons to one.

---

## 2. Product vision

> CopilotMem is a single self-hosted binary that any OpenAI- or Anthropic-compatible coding assistant can point at on the developer's own workstation. By default it acts as a transparent proxy to GitHub Copilot. Opt-in middleware adds persistent memory and prompt compression. The vanilla proxy path is guaranteed to work even if every middleware fails.

Two invariants govern the design:

1. **Vanilla always works.** With all middleware disabled or broken, CopilotMem must behave as a pure request forwarder: input identical to today's Copilot proxies produces identical output. No extension can degrade the base contract.
2. **Extensions fail open.** Each middleware stage runs inside an isolation boundary. A crash, timeout, or misconfiguration in an extension results in that stage being skipped for the affected request. The request continues down the pipeline as if the stage were disabled. The developer is notified via logs and health endpoints, not by broken requests.

These invariants exist because the observed failure mode of coupled tools is precisely the opposite: memory infrastructure gets in the way of the request itself. CopilotMem is designed to make that impossible.

---

## 3. User and use cases

### 3.1 The user

**One developer, working on their own workstation, running one or more AI coding assistants concurrently across several projects.**

Concretely: someone who has Claude Code open in project A on one monitor, Copilot CLI running in project B in a terminal, and occasionally uses Codex or curl to test API responses. They pay for GitHub Copilot and want its quota to reach Claude and GPT models through any of those tools. They want the assistant to remember what they were doing in each project last week, and they don't want to pay more tokens than necessary for large prompts.

### 3.2 Use cases in scope

**Multi-session, multi-project on one machine.**

- Concurrent sessions from different clients (Claude Code + Copilot CLI + Cursor) all proxied through the same CopilotMem instance.
- Each session is attributed to its project (usually by working directory) so memory queries can be scoped: "show me what I did last time in OpenBBTechnical" without dragging in unrelated projects.
- Session identity is client-provided when possible (a client's own session UUID passes through as a header) with a working-directory fallback when clients don't set one.
- Cross-project search when the developer wants it: "have I ever debugged a Copilot proxy port collision before?" should hit results across every project.

**Local, offline-tolerant.**

- Everything runs on the developer's machine.
- No cloud services beyond the configured upstream LLM provider.
- Memory queries and viewer work without an internet connection.

**Reproducible across workstations.**

- The developer occasionally switches machines (laptop → desktop, personal → work). CopilotMem's state — memory database, config, upstream tokens — should export and import cleanly. Not as a sync feature, but as a manual portability guarantee.

### 3.3 Non-goals

CopilotMem is **not** designed for:

- **Multiple users.** No API keys, no per-user quotas, no role-based access. If shared use ever becomes a requirement, that is a separate product.
- **Team memory sharing.** Memory captures are private to one developer's local database.
- **Hosted or remote deployment.** No cloud version, no VPS install guide, no Kubernetes chart. Localhost only.
- **Multi-tenant proxying.** One machine, one instance, one upstream identity (the developer's own Copilot account).
- **Being a coding assistant itself.** It sits under one.
- **Being a vendor-agnostic universal LLM router.** V1 targets GitHub Copilot as upstream. Alternative providers may come later but are not the point.
- **Fine-tuning, model training, or general-purpose observability.**

The single-user constraint eliminates entire categories of complexity: authentication, rate limiting for fairness (versus rate limiting for TOS compliance, which stays), team memory namespacing, session-id conflict resolution across users, and permission systems.

---

## 4. Product principles

The design derives from four principles, in priority order:

1. **The proxy contract is inviolable.** Every request that a client would successfully send today must succeed identically with CopilotMem in the middle. This is testable and will be enforced by contract tests.
2. **Local-first storage.** All memory, compression state, and configuration live in the user's home directory. No hosted dependencies. No network calls other than to the configured upstream provider.
3. **Single runtime, single database, single process.** One binary. One SQLite file. External dependencies (Python for optional ML compression, a vector store for optional semantic search) are opt-in and never installed by default.
4. **Windows is a supported platform, tested first.** File-locking, process-lifecycle, and encoding assumptions that hold on Unix but break on Windows are a known category of bug. Feature acceptance requires a passing Windows test run.

---

## 5. Functional requirements

### 5.1 Core proxy (always on)

The core proxy implements the same functional contract as an OpenAI-and-Anthropic-compatible GitHub Copilot translation layer. Specifically:

| Endpoint | Direction | Purpose |
|---|---|---|
| `POST /v1/chat/completions` | OpenAI-shape in and out | Direct pass-through to Copilot's OpenAI-compatible API |
| `POST /v1/messages` | Anthropic-shape in, translated | Received in Anthropic format, translated to OpenAI internally, translated back on response |
| `POST /v1/messages/count_tokens` | Anthropic-shape | Token counting for message payloads |
| `POST /v1/embeddings` | OpenAI-shape | Embeddings pass-through |
| `GET /v1/models` | Both shapes | Model list; forced-model override applied here if configured |
| `GET /v1/usage` | HTML | Human-readable usage dashboard for the developer's own quota |
| `GET /token` | JSON | Current upstream token state |

The core also owns:

- **Upstream authentication**: GitHub Copilot device-code OAuth flow, token refresh, and secure token storage. This is the developer's own Copilot account.
- **Streaming support**: Server-Sent Events for both OpenAI and Anthropic wire formats, with correct translation of streaming chunk boundaries.
- **Model aliasing**: A single configurable "force model" that overrides whatever model the client requested, useful when the paid subscription only permits certain model IDs.
- **Error translation**: Upstream errors are translated back to the client's request shape (an Anthropic client receives Anthropic-shaped errors even when the underlying Copilot response was OpenAI-shaped).
- **TOS-compliance rate limiting**: A default upstream request rate limit is enforced to keep Copilot usage within its terms of service. This is not user-facing rate limiting (there is only one user); it exists to prevent inadvertent bulk-request patterns that could trip Copilot's abuse detection.

The core is what remains when every extension is disabled via `copilotmem serve --vanilla`.

### 5.2 Memory extension (opt-in)

When enabled, the memory extension captures LLM traffic and makes it queryable across sessions and projects.

**Capture** (automatic on every request):
- Requests are recorded to the local database, keyed by session ID (from header, cookie, or working-directory fallback) and project (from header or working-directory heuristic).
- Both user prompts and assistant responses are stored verbatim.
- Tool-use events within Anthropic-shape requests are recorded as structured children of the containing prompt.
- Capture is fire-and-forget: recording happens after the response is streamed to the client, so it cannot delay the request path.

**Session and project identity**:
- **Session ID resolution order**: (1) explicit `X-CopilotMem-Session` header from the client, (2) client-native session identifier if the wire format includes one, (3) a stable hash of client IP + user-agent + working directory. Order (3) means two concurrent Claude Code sessions in the same project directory would collide; the client is expected to disambiguate by setting the header, which every supported client does.
- **Project resolution order**: (1) explicit `X-CopilotMem-Project` header, (2) client's reported working directory converted to a project slug, (3) `default`. This handles the concurrent-projects case cleanly: each Claude Code launched from a different directory automatically ends up in a different project bucket.
- **Concurrent sessions are first-class.** The datastore assumes multiple active sessions at any moment. Writes are serialized through SQLite's WAL; reads are non-blocking.

**Summarization** (optional sub-capability):
- Sessions and individual observations can be LLM-summarized for compact retrieval later.
- Summarization uses the proxy itself as its LLM backend — no separate provider account or auth chain is required. This solves the "the summarizer needs a separate Anthropic OAuth login" problem observed with existing tools. **This is the single-auth-chain rule (§7.2.5), enforced by contract test `tests/contract/no-second-auth.test.ts`.** Every internal LLM call sets `X-CopilotMem-Extensions: none` as a recursion guard; the proxy detects the marker and refuses to re-enter extensions.
- Summarization is throttled and quota-aware so it does not exhaust upstream credits.

**Retrieval**:
- HTTP endpoints for listing projects, listing sessions per project, and full-text search (per-project or cross-project).
- MCP server subcommand that exposes memory search as a tool for external MCP-compatible clients (Claude Desktop, Cursor, Codex, etc.), so the developer can query memory from inside a running assistant session.
- Optional context injection: recent relevant memories can be automatically prepended to the system message of new requests, opt-in per-project.

**Data lifecycle**:
- Local retention policy (default: keep forever; configurable time-based or size-based expiry).
- Export to JSON or JSONL for archival or portability across the developer's own machines.
- Import from claude-mem's database on first run, so existing memory is not lost.

### 5.3 Compression extension (opt-in)

When enabled, the compression extension shrinks prompts before they reach the upstream provider.

**Algorithms**:
- **JSON compression**: Reduces token count of structured JSON payloads by tokenizing repeated keys and paths.
- **Code-aware compression**: Uses AST parsing (via `tree-sitter`) to shorten source code while preserving semantic meaning, supporting the languages tree-sitter has grammars for.
- **Prose compression** (optional): Uses an ML model to compress natural-language prose. Requires a Python sidecar and model download; opt-in only.
- **Cache-prefix alignment**: Normalizes the prefix of repeated requests so the upstream provider's KV cache hits more often. Not compression per se, but co-located because it operates on the same request payload.

**Reversibility**:
- Compressed content is stored locally alongside the compressed form. When the assistant needs the original (via a `retrieve` tool call), CopilotMem returns it.
- The developer can opt out of reversibility to save disk if they trust the compression to be lossless-for-purpose.

**Content-type routing**:
- The compression extension inspects request content and dispatches to the appropriate algorithm automatically. The developer can override per-request via header.

**Diagnostics**:
- Compression ratio, tokens saved, and before/after samples are exposed at `/compress/stats` for auditing quality. Useful for the developer to decide whether a given compression setting is actually helping.

### 5.4 Configuration and toggling

- Configuration lives in `<state>/config.toml` (see §7.5 for `<state>` resolution).
- CLI overrides: `--extensions memory,compress` or `--extensions -memory` (leading dash disables) or `--vanilla` (kill switch).
- Per-request overrides via header: `X-CopilotMem-Extensions: -compress` disables compression for one request; `X-CopilotMem-Extensions: none` runs vanilla for one request.
- Runtime toggle endpoint `POST /admin/extensions/toggle` for enabling or disabling without restart. Bound to localhost only; no auth needed because the machine has one user.

### 5.5 Observability

- `GET /health` reports vanilla status (always) and, with `?extensions=1`, per-extension health.
- Structured logs in JSONL, one file per day, in `<state>/logs/` (see §7.5 for `<state>` resolution).
- Every request assigned a request ID, echoed in response headers, present in every log line for the request. This is essential when debugging why a specific prompt behaved oddly across concurrent sessions.

---

## 6. Non-functional requirements

| Category | Requirement |
|---|---|
| **Startup time** | Cold start under 2 seconds on developer hardware (SSD, modern laptop). |
| **Vanilla latency overhead** | Under 5ms p50 per request compared to a bare proxy of the same wire format. |
| **Memory extension overhead** | Under 50ms p50 per request; under 200ms p99. Capture happens async so the client never blocks. |
| **Compression overhead** | Variable by algorithm; JSON under 20ms per request, code under 100ms, prose bounded by ML model latency and opt-in only. |
| **Memory footprint** | RSS under 350MB steady state with default extensions enabled (up from 200MB in v0.4 to account for the headroom compression sidecar subprocess; the main CopilotMem process alone stays under 200MB). |
| **Disk footprint** | Database growth bounded by configurable retention policy; default cap 5GB with warn at 1GB. |
| **Concurrency** | Handle at least 5 concurrent sessions from different clients without cross-talk or performance degradation. |
| **Platform support** | Windows 11, macOS 14+, Linux (glibc 2.31+ / musl). Windows is the first-tested platform. |
| **Runtime** | Single binary via Bun's compile output; no runtime install required. Node.js compatibility maintained but not required. |
| **Persistence** | SQLite via `bun:sqlite`. No external database. WAL mode enabled. |
| **Security** | No credentials in logs. Upstream tokens stored via OS keyring where available, filesystem with restrictive permissions as fallback. Localhost-only bind by default; explicit opt-in required to bind other interfaces. |
| **Portability** | State export/import (`copilotmem export-state`, `copilotmem import-state`) so the developer can move their setup between their own machines. |

---

## 7. Repository and codebase strategy

### 7.1 Primary development repository

Primary development happens in a **new dedicated repository**:

```
copilotmem/
```

This repository owns:
- The CopilotMem binary source code
- The pipeline runtime and extension loader
- All extensions maintained by the project (memory, compress, cache-align)
- Documentation, tests, CI, and release engineering
- The single canonical build

**Rationale for a new repository rather than forking one of the existing projects:**

- The product's charter is distinct from any of its inputs. It is not "copilot-api plus features"; it is a new integrated product. Naming it separately signals that clearly.
- License clarity: starting fresh avoids inheriting the copyright status of a reverse-engineered proxy or a claude-specific tool. Each imported piece can be relicensed cleanly with attribution.
- Testing surface: CopilotMem needs contract tests that its imported pieces do not have. A new repo can be TDD from day one.

### 7.2 Source projects and their roles

**v0.5 aggregator model.** All three source projects are wrapped as **git submodules** under `vendor/`. CopilotMem's value is the unified surface (one HTTP endpoint, one config, one database, one auth relationship with Copilot), not the unified codebase. Language decides integration mode:

- **Same-language submodules** (`copilot-api`, `claude-mem`, both TypeScript) → imported in-process via ESM.
- **Language-mismatched submodules** (`headroom`, Python + Rust) → run as a supervised subprocess with IPC over Unix Domain Socket (Linux/macOS) or Named Pipe (Windows).

The aggregator principle is uniform; only the process boundary differs.

**Selective import is mandatory.** Every submodule's source tree contains files that must **not** be imported by CopilotMem — for `claude-mem` in particular, the summarizer / worker / hooks / installer subsystems introduce a second Anthropic auth chain that would break the single-auth-chain rule (§7.2.5). The per-submodule denylists below are enforced by contract test.

#### 7.2.1 Copilot API proxy (upstream: `prajoria/copilot-api`)

**Role**: **Git submodule at `vendor/copilot-api/`, imported in-process.**

The Copilot proxy — its OpenAI/Anthropic translation logic, GitHub Copilot device-code authentication flow, and route handlers — is tracked as a git submodule. CopilotMem's `src/core/` contains only **glue code**: thin adapters that import from the submodule, extend where needed, and expose the results through CopilotMem's unified request/response types.

**Import allowlist** (safe subsystems):
- `src/routes/messages/{non-stream,stream}-translation.ts` — protocol translation
- `src/services/copilot/*` — upstream client
- `src/services/github/*` — device-code OAuth (this **is** the sanctioned auth path — Copilot upstream — not a competing chain)

**Auth surface**: GitHub Copilot device-code flow, which **is** CopilotMem's single auth chain. No conflict.

**Ongoing relationship**: pin the submodule to a specific SHA in `main`. Bump the SHA in dedicated PRs tracked by their own issues. Feature branches may temporarily point at unmerged upstream branches when adopting pre-release upstream fixes. Bug fixes flow via the developer's working fork clone at `H:\masterswork\git\OpenBBTechnical\copilot-api\` → push → `git submodule update` here.

#### 7.2.2 Claude-mem (upstream: `prajoria/claude-mem`, forked from `thedotmack/claude-mem`)

**Role**: **Git submodule at `vendor/claude-mem/`, imported selectively in-process. Summarizer replaced by a CopilotMem-native shim.**

Change from v0.4: the memory extension is no longer a ~5 kLOC port; it is a **wrapper** around specific claude-mem subsystems, plus a small shim (~100 LOC) that replaces the LLM-calling code path.

**Import allowlist** (safe — no auth surface):
- `src/storage/sqlite/*` — schema, migrations, connection pool
- `src/services/context/*`, `src/services/context-generator.ts` — retrieval logic
- `src/services/transcripts/*` — Claude Code transcript parsing
- `src/ui/*` — HTMX viewer (server-rendered HTML)

**Import denylist** (auth-touching — must be replaced by shims in `src/extensions/memory/`):
- `src/shared/EnvManager.ts` — manages Claude Desktop OAuth tokens (violates §7.2.5)
- `src/services/worker/ClaudeProvider.ts` — spawns `claude` CLI with OAuth env (violates §7.2.5)
- `src/services/worker/knowledge/KnowledgeAgent.ts` — LLM summarizer via OAuth env (violates §7.2.5)
- `src/server/runtime/create-server-service.ts` — reads `ANTHROPIC_API_KEY` (violates §7.2.5)
- `src/cli/*`, `src/hooks/*`, `src/npx-cli/*` — Claude Code plugin surface (violates the no-plugin rule in §7.5)

**The summarizer shim** (`src/extensions/memory/summarizer.ts`) replaces the ~2 kLOC of `ClaudeProvider + KnowledgeAgent + EnvManager` with ~100 LOC of code that POSTs to `http://127.0.0.1:4242/v1/messages` with `X-CopilotMem-Extensions: none`. This is the concrete mechanism of the single-auth-chain rule.

**Ongoing relationship**: monitor upstream for schema changes; bump the submodule SHA in dedicated PRs. Bug fixes to claude-mem itself flow via `prajoria/claude-mem` (your fork) → push → `git submodule update`. Never edit `vendor/claude-mem/` in-place from this repo.

#### 7.2.3 Headroom (upstream: `prajoria/headroom`)

**Role**: **Git submodule at `vendor/headroom/`, run as a supervised subprocess (IPC over UDS / Named Pipe).**

Change from v0.4: compression algorithms are no longer ported to TypeScript; they run in headroom's native Python+Rust process, spawned and supervised by CopilotMem. The compression extension in `src/extensions/compress/` is a thin **IPC client** (~200 LOC) that speaks headroom's protocol.

**Why subprocess, not in-process**:
- Language mismatch. Bun cannot import Python or Rust modules directly.
- **Bundling still works**: the CopilotMem release ships as a bundle (Bun binary + pre-built headroom sidecar + submodule copies), not as one file. Users install one bundle, not three projects.
- **Auth surface**: compression operates on prompt bytes and does not call any LLM API. No second auth chain (verified during Phase 2 wiring per §7.2.5 audit).

**Import allowlist** (via IPC — no direct code imports, but the subprocess must be launched in a mode that stays inside these bounds):
- SmartCrusher (JSON compression)
- CodeCompressor (tree-sitter-based code compression)
- CCR reversible storage
- CacheAligner

**Import denylist** (must be disabled via headroom's own config when the subprocess is launched):
- Any hosted-inference model calls (headroom's optional prose-compression path — verify before enabling; prose compression stays opt-in per §5.3)
- Any auth/telemetry endpoints that phone home

**Ongoing relationship**: pin submodule SHA; bump in dedicated PRs. Headroom's build produces platform-specific binaries; the CopilotMem release bundle carries the correct one per platform. First-run instructions document how to build the sidecar from source if the pre-built binary is missing.

#### 7.2.4 Summary of aggregator model

| Source project | Strategy | Location | Integration mode | Auth-surface handling |
|---|---|---|---|---|
| copilot-api | Submodule | `vendor/copilot-api/` | In-process (ESM import) | Its auth **is** CopilotMem's single auth chain |
| claude-mem | Submodule | `vendor/claude-mem/` | In-process (selective ESM import) | Denylist blocks summarizer/worker/hooks; shim replaces summarizer |
| headroom | Submodule | `vendor/headroom/` | Supervised subprocess (UDS / Named Pipe) | No LLM calls in the compression path; audited before enabling |

#### 7.2.5 The single-auth-chain rule (non-negotiable)

**No caller of any CopilotMem component may require a Claude/Anthropic OAuth login, API key, or credential that is separate from the Copilot upstream token CopilotMem already holds.**

Every LLM call in the whole system — including CopilotMem's own internal summarizer calls, memory-context calls, and health-probe calls — routes through the proxy itself at `http://127.0.0.1:4242`, using the **recursion-guard header value** `X-CopilotMem-Extensions: none` so the proxy detects the internal call and refuses to re-enter extensions (avoiding infinite loops).

**Concrete meaning per subsystem**:

- **`vendor/copilot-api/`** — its OAuth flow **is** the single sanctioned auth chain. No shim needed; imported as-is.
- **`vendor/claude-mem/`** — every subsystem is audited (§7.2.2 denylist). Auth-touching files (`EnvManager`, `ClaudeProvider`, `KnowledgeAgent`, `create-server-service`) are on the denylist and replaced by CopilotMem-native shims that POST to the proxy.
- **`vendor/headroom/`** — the subprocess is launched in a config that disables any hosted-inference or telemetry endpoint. Compression itself does not authenticate; only the optional prose-compression ML model does, and that model is local-only per §10.7.

**Enforcement** — three layers, cheapest first:

1. **Grep-based contract test** `tests/contract/no-second-auth.test.ts` — scans all `src/**/*.{ts,tsx}` on every commit for a denylist of forbidden strings (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_MEM_ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `buildIsolatedEnvWithFreshOAuth`, `readClaudeOAuthToken`, `api.anthropic.com`, `console.anthropic.com`, `claude.ai/api`) and forbidden import paths (`vendor/claude-mem/src/shared/EnvManager*`, `.../ClaudeProvider*`, `.../KnowledgeAgent*`, etc.). Failure = commit is blocked in CI.

2. **Audit checklist** — every vendored file goes through the three-step audit in SESSION-START §9.6 before being added to any import allowlist. If any hit, the file cannot be imported; a shim replaces it.

3. **Recursion-guard header** — proxy detects `X-CopilotMem-Extensions: none` on incoming requests, refuses to re-enter the extension pipeline, guaranteeing termination.

**Why this rule matters**: the debugging saga that motivated CopilotMem's existence (SESSION-START §9.4) traced back to exactly this failure mode — `claude-mem`'s summarizer required its own Anthropic OAuth login separate from the Copilot proxy's own auth, defeating the point of the proxy. CopilotMem exists to solve this. Losing this rule reduces CopilotMem to a distribution convenience for tools that still don't cooperate; keeping it is what makes the product architecturally different from a naive "aggregator of tools."

### 7.3 Repository layout inside CopilotMem

```
copilotmem/
├── vendor/
│   ├── copilot-api/                     # git submodule → prajoria/copilot-api (TS, in-process)
│   ├── claude-mem/                      # git submodule → prajoria/claude-mem (TS, selective in-process, see §7.2.2 denylist)
│   └── headroom/                        # git submodule → prajoria/headroom (Python+Rust, supervised subprocess)
├── src/
│   ├── core/                            # Vanilla proxy; always active
│   │   ├── proxy.ts                     # entry, wires routes to pipeline
│   │   ├── routes/                      # thin adapters that call into vendor/copilot-api
│   │   ├── translation/                 # thin adapters (Anthropic ↔ OpenAI)
│   │   ├── upstream/                    # thin adapters over vendor/copilot-api services
│   │   ├── auth/                        # thin adapter over vendor/copilot-api's device-code flow
│   │   └── rate-limit.ts                # TOS-compliance limiter (core; see §10.9)
│   ├── extensions/                      # Each self-contained
│   │   ├── memory/                      # ADAPTER over vendor/claude-mem/ per §7.2.2 allowlist
│   │   │   ├── summarizer.ts            # SHIM — replaces claude-mem's ClaudeProvider/KnowledgeAgent/EnvManager;
│   │   │   │                              # posts to http://127.0.0.1:4242 with X-CopilotMem-Extensions: none
│   │   │   ├── storage.ts               # thin wrapper over vendor/claude-mem/src/storage/sqlite/
│   │   │   └── retrieval.ts             # thin wrapper over vendor/claude-mem/src/services/context/
│   │   ├── compress/                    # IPC CLIENT to vendor/headroom/ subprocess
│   │   │   ├── client.ts                # UDS / Named Pipe client
│   │   │   └── supervisor.ts            # spawn / health / restart of headroom sidecar
│   │   ├── cache-align/                 # thin over headroom's CacheAligner (via subprocess IPC)
│   │   └── tos-rate-limit/              # (moved to core/rate-limit.ts; kept here as compat shim if needed)
│   ├── pipeline/                        # New middleware runtime
│   │   ├── types.ts                     # RequestContext, ResponseContext, ProxyExtension
│   │   ├── isolation.ts                 # try/catch + timeout wrapper (fail-open per §2)
│   │   ├── loader.ts                    # dynamic import of extensions
│   │   └── executor.ts                  # 9-stage pipeline runner per §8.1
│   ├── cli/                             # Subcommands (serve, auth, search, config, mcp, export-state)
│   ├── shared/                          # Config, types, logger, path resolution, pidfile (see §7.5)
│   └── migrations/                      # SQLite schema migrations per extension
├── tests/
│   ├── contract/                        # Vanilla-invariant + no-second-auth tests (§7.2.5)
│   ├── coexistence/                     # §7.5 assertion: run alongside copilot-api + claude-mem
│   ├── integration/
│   └── unit/
├── scripts/
│   ├── build.ts
│   ├── bump-copilot-api.ts              # helper to bump submodule + regenerate adapter stubs
│   ├── bump-claude-mem.ts               # same for claude-mem submodule
│   ├── bump-headroom.ts                 # same for headroom submodule
│   ├── install-hooks.{sh,ps1}           # sets git config core.hooksPath .githooks (see SESSION-START §8.5)
│   ├── install.ps1                      # Windows first-run bootstrap
│   ├── file_phase_issues.py             # bulk GitHub-issue filer for phase batches (see #6)
│   └── copilotmem_project.json          # persisted project #6 IDs (fields, options, epic)
├── .githooks/
│   └── commit-msg                       # enforces issue-first rule from #1 (SESSION-START §8.5)
├── docs/
│   ├── PRD.md                           # this document
│   ├── ARCHITECTURE.md
│   ├── EXTENSIONS.md
│   └── MIGRATION.md
├── .gitmodules                          # tracks all three submodules
├── package.json
├── config.example.toml
└── LICENSE                              # Apache 2.0 (covers glue code + shims; submodules keep their own)
```

### 7.4 What lives outside the repository

- **CopilotMem state directory** — see §7.5 for the exact path.
- **Third-party model weights** (for optional prose compression) — downloaded on first use to `<state>/models/`.
- **User's shell integration** — the launcher script that sets environment variables and invokes the binary. Not part of the repo; provided as templates in `docs/`.

### 7.5 Coexistence with existing tools (namespace separation)

CopilotMem is designed to run **alongside** an existing copilot-api instance and an existing claude-mem plugin during the migration window (see §11). This requires that CopilotMem touches no port, file, directory, or environment variable that either tool already uses.

The following table is the definitive namespace mapping. Any code that reads or writes state must follow it, and the contract-test suite enforces it.

| Resource | copilot-api (existing) | claude-mem (existing) | **CopilotMem (new)** |
|---|---|---|---|
| HTTP port (default) | `4141` | `37777` (worker) | **`4242`** |
| State directory (Windows) | `%USERPROFILE%\.local\share\copilot-api\` | `%USERPROFILE%\.claude-mem\` | **`%LOCALAPPDATA%\copilotmem\`** |
| State directory (Unix) | `~/.local/share/copilot-api/` | `~/.claude-mem/` | **`~/.local/share/copilotmem/`** |
| SQLite database | (none) | `<state>/claude-mem.db` | **`<state>/copilotmem.db`** |
| Log directory | `%USERPROFILE%\.local\share\copilot-api\` | `<state>/logs/` | **`<state>/logs/`** (own state dir) |
| PID file | (implicit) | `<state>/worker.pid` | **`<state>/copilotmem.pid`** |
| Upstream token file | `<state>/github_token` | (none — uses Anthropic OAuth) | **`<state>/upstream_token`** (renamed to signal "any upstream", though Copilot at launch) |
| Config file | (none — CLI args only) | `<state>/settings.json` | **`<state>/config.toml`** |
| Env var prefix | (none) | `CLAUDE_MEM_*` | **`COPILOTMEM_*`** |
| Placeholder API key value | `copilot-proxy` | (n/a) | **`copilotmem-proxy`** |
| Marketplace / plugin cache | (n/a) | `~/.claude/plugins/cache/thedotmack/claude-mem/` | (n/a — no plugin surface) |
| Process title (main) | `node ... copilot-api/dist/main.js` | `bun ... worker-service.cjs` | **`copilotmem serve`** |
| Windows binary shim | (n/a — bun.cmd shim workaround) | (needs bun.cmd shim) | (own binary; no shim dependency) |
| **Compression sidecar IPC socket** (v0.5) | (n/a) | (n/a) | **`<state>/services/headroom/sock`** (Unix Domain Socket on Linux/macOS); **`\\.\pipe\copilotmem-headroom`** (Named Pipe on Windows) |
| **Compression sidecar PID / logs** (v0.5) | (n/a) | (n/a) | **`<state>/services/headroom/{pid,logs/}`** |
| **Recursion-guard header value** (v0.5) | (n/a) | (n/a) | **`X-CopilotMem-Extensions: none`** — set on every internal LLM call; proxy detects marker and refuses to re-enter extensions. See §7.2.5. |

**Rationale for each choice**:

- **Port `4242`**: deliberately non-adjacent to `4141` so muscle memory doesn't cause confusion, still in the "developer tools" range, unassigned by IANA, memorable, and free on the workstations checked during design.
- **`copilotmem` state dir (not `copilot-mem`)**: single-word directory name matches the CLI command and binary name; no hyphen to fat-finger.
- **Windows uses `%LOCALAPPDATA%` instead of `%USERPROFILE%\.local\share`**: `%LOCALAPPDATA%` (`C:\Users\<user>\AppData\Local`) is the Windows-native convention for per-user app state. The `~/.local/share` pattern that copilot-api uses is a Linux XDG convention that works on Windows only by convention. Following the platform convention avoids antivirus false positives and Windows-search indexing surprises.
- **Renamed token file**: `github_token` → `upstream_token`. The rename signals that CopilotMem's auth surface is generic (any future upstream provider), not GitHub-specific, and also makes it obvious this file is not interchangeable with copilot-api's token even though the format is currently identical.
- **Env var prefix `COPILOTMEM_`**: does not collide with `CLAUDE_MEM_`, `COPILOT_API_`, `ANTHROPIC_`, `OPENAI_`, or any GitHub CLI variable. Case-consistent uppercase.
- **No plugin/marketplace surface**: CopilotMem is not a Claude Code plugin, does not install into `~/.claude/plugins/`, and does not participate in any plugin marketplace's cache. This alone eliminates an entire class of coordination bugs observed with claude-mem.

**Coexistence test**: a supported migration scenario has copilot-api running on `:4141`, claude-mem's worker running on `:37777`, and CopilotMem running on `:4242` — all simultaneously on the same machine. The developer can point one client at CopilotMem while other clients continue to use the existing stack. Nothing collides. This scenario is a required passing test before v0.1 ships.

**Overrides**: every default in the table above is overridable via config (`COPILOTMEM_PORT`, `COPILOTMEM_STATE_DIR`, etc.) for the rare case where a developer needs a different port or state path.

---

## 8. System architecture

### 8.1 Request pipeline

Every incoming request flows through a fixed sequence of stages. Stages that are extensions can be skipped; stages that are core cannot.

| Stage | Role | Type |
|---|---|---|
| 1 | Ingress translation (client wire format → internal representation) | Core |
| 2 | TOS-compliance rate limiting | Core (default) / Extension (configurable) |
| 3 | Memory injection (prepend recalled context to system message) | Extension |
| 4 | Compression (transform prompt payload) | Extension |
| 5 | Cache-prefix alignment | Extension |
| 6 | Upstream call to Copilot | Core |
| 7 | Response capture to memory (async, off request path) | Extension |
| 8 | Decompression / retrieval-token handling | Extension |
| 9 | Egress translation (internal representation → client wire format) | Core |

Each extension implements a common interface (see §8.3) and is loaded via dynamic import. The pipeline runner catches any thrown exception, logs it with the request ID, marks the extension as errored for that request, and continues to the next stage.

### 8.2 Data model

A single SQLite database, one file, one connection pool. Extensions declare their tables via migrations that run at first-load.

Core tables:
- `requests` (id, ts, session_id, project, model, endpoint, tokens_in, tokens_out, latency_ms, cached, request_id)
- `sessions` (id, first_seen, last_seen, project, cwd, client_kind, title)
- `projects` (name, first_seen, last_seen, tags)

Memory extension tables:
- `prompts` (id, session_id, ts, role, content_raw, content_compressed, compression_algo)
- `observations` (id, session_id, prompt_id, ts, summary, model_used, tokens_used)
- `session_summaries` (id, session_id, ts, summary)
- FTS5 virtual tables for full-text search over prompts and observations

Compression extension tables:
- `ccr_originals` (hash, ts, content, size_bytes, compression_ratio, session_id)
- `compression_stats` (day, algorithm, requests_touched, tokens_before, tokens_after)

The `sessions.client_kind` column records which tool initiated the session (`claude-code`, `copilot-cli`, `cursor`, `codex`, `curl`, `unknown`), so cross-client memory queries can filter or group by tool if the developer wants.

All tables include an `extension_version` column to support schema migrations without cross-extension coupling.

### 8.3 Extension contract

```typescript
export interface RequestContext {
  requestId: string;
  clientWireFormat: 'openai' | 'anthropic';
  sessionId: string;
  project: string | null;
  payload: unknown;         // extension-visible mutable request payload
  headers: Headers;
  metadata: Map<string, unknown>;  // cross-extension scratchpad
}

export interface ResponseContext extends RequestContext {
  response: unknown;
  upstreamLatencyMs: number;
  tokensIn: number;
  tokensOut: number;
}

export interface ProxyExtension {
  readonly name: string;
  readonly order: number;                    // pipeline position
  readonly enabled: boolean;                 // set at load time from config

  onRequest?(ctx: RequestContext): Promise<RequestContext | void>;
  onResponse?(ctx: ResponseContext): Promise<ResponseContext | void>;
  onError?(err: Error, ctx: RequestContext): Promise<void>;
  healthcheck?(): Promise<{ok: boolean; detail?: string}>;
  migrations?(): readonly Migration[];
}
```

Extensions are loaded by dynamic import from `src/extensions/*/extension.ts` at proxy startup. Failed loads log a warning and mark the extension unavailable; the proxy continues with the remaining extensions.

### 8.4 Concurrency and process model

- **Single Node/Bun process.** No multi-process supervisor. The developer runs one instance on their machine.
- **HTTP server** handles requests in the main event loop; CPU-bound work (compression AST parsing, ML model calls) runs in a worker thread pool.
- **Multiple concurrent sessions** from different clients are the norm: the pipeline is designed to handle several in flight at once. Session identity is per-request, so concurrent Claude Code + Copilot CLI + curl sessions all coexist without coordination.
- **Optional Python sidecar** for prose compression is a persistent subprocess with an IPC channel; it is spawned lazily on first prose-compression request and reaped on idle timeout.
- **The proxy owns a single writable connection to SQLite**; reads happen via a separate read-only connection pool. WAL mode ensures readers do not block writers.

### 8.5 Failure and recovery

- **Extension crash during request**: caught, logged, extension skipped for that request only. The client sees a normal response.
- **Extension crash at load**: extension marked unavailable, remaining extensions loaded normally, health endpoint reports the failed extension. Proxy starts successfully.
- **Upstream provider unavailable**: request fails cleanly with a translated error in the client's wire format; retry policy is the client's responsibility (documented as such).
- **Database locked**: async writes retry with exponential backoff; sync reads use WAL so they proceed regardless.
- **Port in use at startup**: the launcher checks and either exits with a clear message or (in `--force` mode) kills the previous owner via pidfile and restarts. This directly addresses a known operational failure mode observed with the source projects.
- **Corrupt state file**: on startup, if the SQLite database, pidfile, or config file is malformed, CopilotMem logs the problem and either recovers (regenerates the pidfile, resets the WAL) or fails with an actionable message and the path to the offending file. It never silently pretends everything is fine.

---

## 9. User experience

### 9.1 First run

A first-time user completes setup in three steps:

1. Install the CopilotMem binary (one command, no runtime dependencies).
2. Run `copilotmem auth` and complete the GitHub Copilot device-code flow.
3. Run `copilotmem serve`. The proxy is now available at `http://127.0.0.1:4242`.

Any tool that speaks OpenAI or Anthropic can now be pointed at the proxy by setting its base-URL environment variable. The developer typically wraps this in a launcher script (see §9.5).

### 9.2 CLI surface

```
copilotmem serve [--port N] [--extensions LIST] [--vanilla] [--config PATH]
copilotmem auth                            # GitHub Copilot device flow
copilotmem status                          # show enabled extensions and health
copilotmem search "query" [--project X]    # full-text search memory
copilotmem sessions [--project X]          # list captured sessions
copilotmem export --session ID [--format json|jsonl]
copilotmem export-state PATH               # dump full state (config + db + tokens) for machine migration
copilotmem import-state PATH               # restore from exported state
copilotmem config [get|set] KEY [VALUE]
copilotmem serve-mcp                       # expose memory as MCP server for external clients
copilotmem migrate --from claude-mem PATH  # one-shot import from claude-mem database
copilotmem doctor                          # diagnostic report for issue reporting
```

### 9.3 HTTP surface

**Core endpoints** (always present):
- `POST /v1/chat/completions`, `POST /v1/messages`, `POST /v1/messages/count_tokens`
- `POST /v1/embeddings`, `GET /v1/models`, `GET /v1/usage`, `GET /token`
- `GET /health`

**Memory extension endpoints** (present when memory enabled):
- `GET /memory/api/projects`
- `GET /memory/api/sessions?project=X`
- `GET /memory/api/search?q=Y&project=X` (project filter optional; omit for cross-project)
- `GET /memory/ui` — browser-friendly viewer

**Compression extension endpoints** (present when compress enabled):
- `GET /compress/stats`
- `POST /compress/retrieve` — retrieves original content by CCR reference

**Admin endpoints** (present when configured):
- `POST /admin/extensions/toggle`

All endpoints bind to `127.0.0.1` by default. Binding another interface requires explicit `--bind` argument, and the developer will see a warning about the single-user assumption being violated.

### 9.4 Per-request overrides

Clients can influence CopilotMem's behavior per request via headers:

- `X-CopilotMem-Session: <id>` — override session grouping (this is how concurrent sessions from the same client disambiguate themselves)
- `X-CopilotMem-Project: <name>` — override project attribution
- `X-CopilotMem-Extensions: -compress,-memory` — disable specific extensions
- `X-CopilotMem-Extensions: none` — vanilla for this request

Headers take precedence over configuration.

### 9.5 Launcher script (recommended template)

A template launcher is provided for each platform. On Windows:

```bat
@echo off
start /B copilotmem serve --extensions memory,cache-align
set "ANTHROPIC_BASE_URL=http://127.0.0.1:4242"
set "ANTHROPIC_API_KEY=copilotmem-proxy"
%*
```

The developer invokes it as `start-with-copilotmem.bat claude --model claude-opus-4.7` or `start-with-copilotmem.bat codex` from any project directory. The child process inherits the environment and gets attributed to the correct project automatically via working-directory detection.

For concurrent sessions, the launcher pattern works identically — the developer opens two terminals, `cd`s each into a different project, and invokes the launcher in each. The proxy is shared (it started once, in the first launcher); the two sessions attribute themselves to different projects.

---

## 10. Design decisions

Decisions previously left open have been resolved as follows:

### 10.1 Runtime: Bun (with Node compatibility)

**Decision**: Bun is the primary runtime and target. Code is written to remain executable under Node.js for portability, but Bun is the tested and shipped configuration.

**Rationale**: Bun ships `bun:sqlite` natively (no separate SQLite binding install), starts faster than Node, and compiles to a single executable via `bun build --compile`. Node compatibility is retained so contributors without Bun installed can still run tests. The developer downloads a pre-built binary and never sees either runtime.

### 10.2 HTTP framework: Hono

**Decision**: Hono is used as the HTTP framework.

**Rationale**: Hono is lightweight (~15KB), works natively on both Bun and Node, has built-in support for middleware chains (aligning with the extension model), and unlike Express does not carry legacy baggage. It also serves static assets well, which the memory viewer needs.

### 10.3 Memory viewer: HTMX + server-rendered HTML

**Decision**: The memory viewer is a server-rendered HTML application enhanced with HTMX, not a React SPA.

**Rationale**: A React application requires a build step, ships a large runtime, and adds a JavaScript bundle to what is fundamentally a data-browsing UI. HTMX renders on the server, streams updates via SSE (which CopilotMem needs anyway for streaming responses), and keeps the viewer to under 100KB of hand-written HTML/CSS. The developer who wants a richer UI can build one against the JSON API.

### 10.4 Configuration format: TOML

**Decision**: Configuration is TOML, not JSON.

**Rationale**: TOML supports comments, is more forgiving of trailing commas and quoting, and is markedly friendlier for hand-editing. JSON is retained for machine-consumed exports and API responses.

### 10.5 Distribution: single install bundle

**Decision** (v0.5): CopilotMem is distributed as a **single install bundle** per platform. Each bundle contains:

1. The CopilotMem binary (`bun build --compile` output).
2. Pre-built `headroom` sidecar binary for the target platform (Python-embedded or standalone Rust binary, depending on final build shape).
3. Submodule copies of `copilot-api` and `claude-mem` (source, since they run in-process via Bun's ESM loader — no separate build artifact).
4. `install-hooks` and first-run bootstrap script.

Distribution channels:
- Pre-built bundles via GitHub Releases (primary channel), one per platform (Windows x86_64, Linux x86_64 glibc, Linux x86_64 musl, macOS arm64).
- `npm install -g copilotmem` and `bun install -g copilotmem` fetch the platform-appropriate bundle.
- Users install one bundle; internally it's three projects, but that's an implementation detail.

**Change from v0.4**: the v0.4 "single binary" framing implied a monolithic executable. That was incompatible with reusing `headroom` (Python + Rust). v0.5 explicitly makes the distribution unit the bundle, not the binary. The user experience remains "download one thing, run one command."

Docker, Homebrew, winget, and chocolatey packaging remain non-goals for v1; contributors welcome to add later.

### 10.6 Licensing

**Decision**: Apache 2.0 for the CopilotMem codebase.

**Rationale**: Compatible with the licenses of all three source projects (claude-mem is Apache 2.0, headroom is Apache 2.0, copilot-api's fork situation is documented and the imported translation code carries appropriate attribution). Apache 2.0 provides explicit patent grant, which matters for anything touching compression algorithms.

### 10.7 Compression algorithms: no patent-encumbered content

**Decision**: Only compression techniques with clear open-source provenance are shipped. The initial set (JSON structural compression, tree-sitter-based code compression, prefix alignment) are all algorithmic and well-established. ML-based prose compression uses only openly-licensed models.

### 10.8 No auth extension

**Decision**: There is no user authentication in v1. The proxy binds to `127.0.0.1` only. Any process on the developer's machine can use it. This is a deliberate consequence of the single-user scope; adding auth would add complexity for no benefit.

### 10.9 TOS-compliance rate limiting is core, not extension

**Decision**: A default upstream rate limit (Copilot terms of service compliance) is part of the core proxy, not a toggleable extension. It can be tuned in config but not disabled.

**Rationale**: Copilot's TOS forbids bulk-request patterns. Making the rate limit toggleable would let the developer accidentally disable it and trip abuse detection. The core enforces a floor; the developer can raise it in config up to a documented maximum but cannot turn it off entirely.

---

## 11. Migration from existing setups

### 11.1 From standalone copilot-api

A user running today's copilot-api replaces it with CopilotMem in vanilla mode. Their client configuration does not change (same base URL, same API key, same wire formats). Verified by contract tests that record a session against copilot-api and replay it against CopilotMem-vanilla, requiring byte-identical responses for a corpus of requests.

### 11.2 From claude-mem

A user running claude-mem's plugin runs `copilotmem migrate --from claude-mem ~/.claude-mem/claude-mem.db` once. Their historical prompts, sessions, and observations are copied into CopilotMem's schema. The claude-mem plugin can then be disabled in Claude Code. Memory query behavior remains available via CopilotMem's search endpoints and MCP server. Existing project attribution is preserved.

### 11.3 From headroom

A user running headroom disables it. If they want compression, they enable CopilotMem's compress extension. Compression state does not migrate (headroom's CCR store uses a different indexing scheme), but this is acceptable — compression benefits are per-request and there is no long-term state that carries meaning across the migration.

### 11.4 From all three concurrently

The recommended migration path is:
1. Install CopilotMem alongside the existing stack. Point one non-critical client at it.
2. Verify vanilla mode works. Migrate claude-mem data.
3. Enable memory extension. Verify searches return expected results across the developer's projects.
4. Enable compression extension. Verify `/compress/stats` shows healthy ratios.
5. Point the primary client at CopilotMem. Retire the old stack.

This gives a rollback path at every step.

---

## 12. Success criteria

The product is successful for v1 when:

| Criterion | Measurement |
|---|---|
| Vanilla mode is a drop-in replacement | Contract-test corpus of 200 recorded requests passes with byte-identical responses. |
| **Single-auth-chain rule holds** (v0.5) | `tests/contract/no-second-auth.test.ts` passes on every commit — no forbidden strings or forbidden imports under `src/`. |
| First-run time is under 5 minutes | Timed from downloading the release **bundle** (v0.5: bundle = CopilotMem binary + headroom sidecar + submodule copies) to seeing a proxied response in a supported client. Measured on a fresh Windows VM. |
| Memory extension does not slow requests | p50 request latency within 50ms of vanilla; p99 within 200ms. Measured under sustained 5 concurrent sessions. |
| Compression achieves stated ratio | Median 40-70% token reduction on a corpus of representative coding-assistant prompts. Reported at `/compress/stats`. |
| Failure isolation holds | Chaos test: extension made to throw on every request. Request success rate remains 100%. |
| Concurrent-session correctness | Two Claude Code sessions in different projects, one Copilot CLI in a third project, all running simultaneously: memory queries return the right project's data for each. |
| Windows parity | Full test suite passes on Windows 11 CI runner. |

---

## 13. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Compression degrades response quality | Medium | Medium | Reversibility opt-in by default. `/compress/stats` shows before/after samples. Per-request opt-out via header. |
| Memory writes slow the request path | Low | High | All writes are async and off the request path. Load-tested under concurrency. |
| **Summarizer / internal call creates recursive loop or second auth chain** (v0.5: elevated) | Medium | **Critical** (violates the single-auth-chain rule from §7.2.5) | Three enforcement layers: (1) `X-CopilotMem-Extensions: none` recursion-guard header on every internal call, detected and rejected on re-entry; (2) `tests/contract/no-second-auth.test.ts` grep-based CI gate; (3) per-vendored-file auth-chain audit per SESSION-START §9.6 before any import. |
| **Vendored submodule import drift** (v0.5) | Medium (a well-meaning refactor imports a denylisted file) | **Critical** (silently introduces a second auth chain) | Same three enforcement layers as above. Denylists in §7.2.2 and §7.2.3. |
| **Headroom subprocess crashes or hangs** (v0.5) | Medium | Medium | Supervisor (`src/extensions/compress/supervisor.ts`) restarts with exponential backoff. Compression stage falls back to no-op if sidecar unavailable (fail-open per §2). `/health?extensions=1` reports sidecar status. |
| **Compression sidecar phones home / requires separate auth** (v0.5) | Low | **Critical** (violates §7.2.5) | Headroom is launched in a config that disables hosted-inference and telemetry endpoints. Audit performed during Phase 2 wiring (issue B5 / A3 successor). |
| Extension crashes at load | High | Low | Loader catches, marks extension unavailable, proxy starts with remaining extensions. Reported at `/health`. |
| Two proxy instances collide on the port | Medium | Medium | Pidfile-based startup handshake. `copilotmem serve --force` cleanly kills the previous owner. |
| Concurrent sessions collide on session ID | Medium | Medium | Every supported client sets its own session ID header; when they don't, the working-directory + client-kind fallback disambiguates. Documented. |
| Prose-compression ML model requires large download | Certain (when opted in) | Low | Opt-in only. Model download is a separate command (`copilotmem compress install-model prose`) with size clearly documented. |
| Copilot terms-of-service compliance | Ongoing | High | Rate limit enforced by core, not toggleable off. Documented prominently. |
| Windows file-locking prevents SQLite operations | Medium (based on observed failures with source projects) | High | WAL mode used. All file operations are atomic-write-then-rename. Antivirus interference tested for. |
| Upstream Copilot API changes | Low per year, high impact when it happens | High | Translation code is isolated in `src/core/translation/` for easy patching. Contract tests catch regressions immediately. |
| **Upstream claude-mem or headroom breaking change** (v0.5) | Medium per year | Medium | Submodule SHAs are pinned in `main`; upstream drift is opt-in via a dedicated bump PR that re-runs the auth-chain audit. |
| Developer forgets to point client at proxy | High | Low | Launcher script templates in `docs/` set the env vars automatically. `copilotmem doctor` includes a check for common misconfigurations. |

---

## 14. Roadmap

**v0.5 revision**: Phase 1 shrinks from 3 weeks to ~1 week because the memory extension is now a wrapper around `vendor/claude-mem/` (plus a summarizer shim) rather than a from-scratch port. Phase 2 similarly shrinks by wrapping `vendor/headroom/` as a supervised subprocess instead of porting compression algorithms.

### Phase 0 — Foundation (weeks 1-2)

**Deliverable**: CopilotMem serves as a byte-identical drop-in for the imported Copilot proxy code. No extensions loaded. All three submodules vendored but only `copilot-api` actively used. Ships **v0.1**.

Tracked as GitHub issues #7-#19 (see epic #3). Sequenced slices:

- **A1-A3** — doc frame revisions + submodule vendor (lands the v0.5 model this document describes).
- **B1** — foundations: `package.json`, `tsconfig`, `bunfig`, `config.example`, CI (Ubuntu + Windows).
- **B2** — shared utilities: `paths`, `config`, `logger`, `pidfile`.
- **B3** — pipeline types (interfaces only; runtime lands after core is proven).
- **B4a** — contract test: vanilla-invariant harness (record + replay). Lands **before** the core it guards.
- **B4b** — contract test: no-second-auth grep-based enforcement. Lands **before** any submodule import.
- **B5** — core proxy: routes, translation, upstream, auth, TOS rate-limit. Wraps `vendor/copilot-api/`.
- **B6** — pipeline runtime: isolation, loader, executor. Wires into `src/core/proxy.ts`; empty extension list = same behavior as B5.
- **B7** — CLI: `serve`, `auth`, `status`, `config`, `doctor-stub`.
- **B8** — isolation + coexistence + concurrency tests.
- **B9** — `docs/ARCHITECTURE.md`, `scripts/install.ps1`, single-bundle build, v0.1 tag.

### Phase 1 — Memory extension (week 3)

**Deliverable**: Memory capture and search work from any client, correctly attributed across concurrent sessions. Uses `vendor/claude-mem/` per §7.2.2 allowlist. Ships **v0.2**.

- Wire `vendor/claude-mem/src/storage/sqlite/*` into `src/extensions/memory/storage.ts`.
- Wire `vendor/claude-mem/src/services/context/*` into `src/extensions/memory/retrieval.ts`.
- Write `src/extensions/memory/summarizer.ts` shim (~100 LOC): POSTs to `http://127.0.0.1:4242/v1/messages` with `X-CopilotMem-Extensions: none`. **Replaces** claude-mem's `ClaudeProvider + KnowledgeAgent + EnvManager`; per-file no-second-auth audit before merge.
- Wire capture into pipeline stages 3 and 7 (per §8.1).
- Wire the HTMX viewer from `vendor/claude-mem/src/ui/*` into `/memory/ui`.
- Implement the claude-mem migration command (`copilotmem migrate --from claude-mem PATH`).
- Extend `tests/contract/no-second-auth.test.ts` denylist as necessary; verify green.

**Estimated shrinkage** vs. v0.4's 3-week plan: schema/query patterns/viewer/summarizer prompts are all inherited from the submodule via import, so ~80% of the code is upstream. What remains is the summarizer shim, capture wiring, and the migration command.

### Phase 2 — Compression extension (weeks 4-6)

**Deliverable**: Prompts are automatically compressed with visible ratio reporting. Uses `vendor/headroom/` as a supervised subprocess. Ships **v0.3**.

- Build supervised-subprocess infrastructure: `src/extensions/compress/supervisor.ts` (spawn, health, restart, pidfile per §7.5).
- Build IPC client: `src/extensions/compress/client.ts` (UDS on Linux/macOS; Named Pipe on Windows).
- Wire pipeline stages 4, 5, 8 to call the IPC client (compression, cache-align, decompression).
- Run auth-chain audit on `vendor/headroom/` (§7.2.3 denylist) before enabling; disable hosted-inference/telemetry in headroom's launch config.
- Implement `/compress/stats` endpoint using headroom's reporting.
- Implement `/compress/retrieve` for CCR reversibility.
- Extend release bundle builder to include the pre-built headroom sidecar per platform.
- Windows sidecar build documented (Python + Rust toolchain on Windows is the hardest part).

**Estimated shrinkage** vs. v0.4's 4-week plan: SmartCrusher, CodeCompressor, CCR, and CacheAligner are all reused as-is via subprocess IPC rather than reimplemented. The new work is the supervisor + IPC + bundle builder — worth ~2-3 weeks but strictly less than porting 4 algorithms in TS.

### Phase 3 — Polish and portability (weeks 7-8)

**Deliverable**: The developer can move CopilotMem between their own machines cleanly and troubleshoot common issues without external help. Ships **v1.0** when stable.

- `copilotmem export-state` / `import-state` (per §6 Portability).
- `copilotmem doctor` full impl (Phase 0 shipped a stub) — reports pidfile status, sidecar health, submodule SHAs, auth-chain audit results, common misconfig checks per §13 last row.
- Windows-first installer script for the release bundle (`scripts/install.ps1` extended from Phase 0).
- End-to-end documentation walkthrough for first-time setup (fresh Windows VM, download bundle, run, curl).
- Publish v1.0.

### Explicitly deferred (not in v1)

- Multiple users, API keys, team memory sharing (out of scope entirely).
- Hosted or remote deployment.
- Web UI beyond the memory viewer.
- Fine-tuning integration.
- Failure-mining that writes back to project files (headroom's `learn` feature).
- Semantic vector search (SQLite FTS is sufficient for v1; vector search is a candidate for v2).
- Additional upstream providers (OpenRouter, Anthropic direct, self-hosted models). Copilot only in v1.
- Docker image, Homebrew, winget, chocolatey packaging.

---

## Appendix A — Terminology

| Term | Meaning |
|---|---|
| Core | Functionality that is always active and cannot be disabled. |
| Extension | Functionality loaded as middleware, individually toggleable. |
| Pipeline stage | A step in the ordered chain of request/response processing. |
| Vanilla mode | Configuration with all extensions disabled, providing pure pass-through behavior. |
| CCR | Compressed Content Retrieval: pairing compressed prompts with locally-stored originals so the LLM can request the original via a tool call. |
| Session | A grouping of requests that share a `session_id`, typically corresponding to one interactive coding session with one client. Multiple sessions can be active concurrently. |
| Project | A grouping of sessions that share a `project` label, typically corresponding to one codebase or working directory. |

---

## Appendix B — Review feedback and recommendations

*Reviewer: engineering review pass against the v0.2 draft. This section is additive commentary; it does not modify the requirements above. Items are grouped by severity so the owner can triage. Nothing here blocks prototyping — but the items marked **Critical** should be resolved before any public positioning of the product, and the **High** items should shape Phase 0/1 design rather than being discovered mid-build.*

### B.1 Overall assessment

This is a strong, unusually coherent PRD. The central insight — that memory, compression, and protocol translation all live at the same HTTP boundary and therefore belong in one process — is correct and well-argued. The two invariants ("vanilla always works", "extensions fail open") give the design a spine that most "let's unify our tools" documents lack. Scope discipline is excellent: the single-user constraint is stated early and consistently used to eliminate whole categories of work. The roadmap is honest about deferrals.

The gaps below are mostly in three areas: (1) the legal/TOS footing of the core proxy, (2) a handful of pipeline-ordering and correctness interactions that the stage table papers over, and (3) some non-functional numbers that are likely unachievable as stated. None are fatal; several change the framing more than the build.

### B.2 Critical

**C1 — The core proxy's legality is understated, and rate-limiting is the wrong mitigation.**
The document frames GitHub Copilot TOS compliance as a *rate-limiting* problem (§5.1, §10.9, §13). Rate limiting addresses bulk-request abuse detection, but it does not address the more fundamental issue: routing Copilot-subscription quota to arbitrary non-GitHub clients (curl, Codex, custom scripts) is very plausibly a TOS violation *regardless of request rate*. copilot-api itself exists in a legal grey zone for exactly this reason. Recommendation: add an explicit, honest "Legal and Terms-of-Service posture" section that (a) states the risk plainly, (b) scopes the product as a personal-use tool the user runs against their own account at their own risk, (c) avoids marketing language that encourages TOS-violating patterns, and (d) confirms no redistribution of GitHub tokens or credentials. Do not lead with "TOS-compliance rate limiting" as though the compliance question is solved — it isn't, and that framing invites trouble.

**C2 — License compatibility of the vendored copilot-api code is asserted, not verified.**
§10.6 says copilot-api's "fork situation is documented and the imported translation code carries appropriate attribution." That is not the same as license compatibility. Reverse-engineered protocol code may carry no license, an incompatible one, or unclear provenance. Apache-2.0-relicensing requires the source to permit it. Recommendation: before Phase 0's import step, confirm the exact upstream license of the specific fork you vendor, record the commit SHA and license text in `docs/`, and if the license is absent or incompatible, reimplement the translation layer clean-room rather than copying. Treat this as a Phase 0 gate, not a footnote.

**C3 — Compression that mutates the outbound payload is a correctness hazard, not just a quality one.**
The risk table (§13) frames compression risk as "degrades response *quality*." For a coding assistant this understates it. Code-aware compression that rewrites source before it reaches the model can cause the model to emit edits against bytes that no longer match the user's file, producing wrong diffs, broken patches, and silent corruption. This is a correctness failure, not a quality one. Additionally, the CCR "model calls a `retrieve` tool" mechanism (§5.3, Appendix A) assumes you can inject a tool into the request — but injecting tools changes the tool list the client sent, which can break clients that validate tool schemas or count tools, and the upstream model has no prior knowledge of your custom tool. Recommendations: (a) default compression **off** and never apply code compression to messages that will drive file edits; (b) restrict v1 compression to lossless structural JSON and cache-prefix alignment (both safe), and treat code/prose compression as experimental behind a loud flag; (c) redesign CCR so retrieval does not depend on the upstream model cooperating with an injected tool — prefer proxy-side expansion of a placeholder token before the upstream call, so the model never needs to "know" about retrieval.

### B.3 High

**H1 — Memory injection (stage 3) and cache-prefix alignment (stage 5) are in tension.**
Injecting recalled context into the system message mutates the prompt *prefix*. Upstream KV-cache hit rates depend on a stable prefix. So stage 3 will systematically *defeat* the cache-alignment stage 5 is trying to achieve, unless injected memory is appended in a cache-stable position (e.g. after the stable system preamble, or as a trailing user-context block rather than a prepend). Recommendation: specify *where* in the message array memory is injected, and make cache-alignment aware of the injected region. As written, enabling both extensions could increase cost rather than decrease it.

**H2 — The session-ID story relies on clients that won't cooperate by default.**
§5.2 and §13 lean on "every supported client sets its own session ID header." In practice, Copilot CLI, Cursor, and Codex do **not** send an `X-CopilotMem-Session` header — that is a custom header this product invented. So the real-world default is the stage-3 fallback (hash of IP + user-agent + cwd), which explicitly collides for two concurrent sessions in the same directory (a common case: two terminals, same repo). Recommendation: make the **launcher script the primary session-ID source** — have it generate a per-invocation UUID and inject it as the header via an env-var-driven wrapper — and describe the raw-client case (no launcher) as best-effort. Reframe the header expectation: the product supplies the session ID via its own launcher, rather than assuming clients do.

**H3 — Capturing streamed responses "fire-and-forget after streaming" requires buffering the full stream.**
To store `content_raw` verbatim (§5.2), the proxy must accumulate every SSE chunk for the life of the stream, then persist after completion. That is fine, but it (a) adds memory pressure proportional to concurrent stream size × concurrency, (b) needs a defined behavior for *aborted* streams (client disconnects mid-response — is a partial observation stored?), and (c) interacts with the 200MB RSS ceiling (§6). Recommendation: specify the buffering strategy, the aborted-stream policy, and confirm the RSS budget accounts for N concurrent buffered streams.

**H4 — Localhost-only is treated as sufficient security, but memory contains secrets.**
Captured prompts frequently contain API keys, tokens, file contents, and proprietary code. Storing them verbatim (§5.2) and exposing them over an unauthenticated `/memory/api/search` and `/memory/ui` (§9.3) means *any* local process — including a malicious npm/pip postinstall script — can read the developer's entire prompt history. "One user, so no auth" (§10.8) conflates *users* with *processes*. Recommendations: (a) note this threat explicitly; (b) consider at-rest encryption or OS-keyring-gated DB access for the memory store, or at minimum restrictive file permissions on the DB (you already do this for tokens); (c) consider a redaction pass on capture for obvious secret patterns; (d) gate the admin toggle endpoint behind a local token even in single-user mode, since a hostile local process is a realistic threat model even when a second human is not.

**H5 — Several NFR numbers look unachievable as stated.**
- *Vanilla latency overhead < 5ms p50* (§6) for a proxy doing full Anthropic↔OpenAI translation *plus* SSE chunk-boundary re-translation is aggressive. JSON parse/serialize of large message arrays alone can exceed this. Recommend measuring against the imported copilot-api baseline early and resetting the target to what "pure forwarder" actually costs, rather than an absolute 5ms.
- *Cold start < 2s* (§6) including SQLite open, WAL recovery, migration checks, and extension dynamic-imports is plausible on Bun but should be validated on Windows-with-antivirus, which is your first-tested platform and historically the slow case.
- *Median 40–70% token reduction* (§12) is a strong claim for mixed coding prompts; structural JSON compression rarely reaches that on prose-heavy or already-terse prompts. Recommend framing as "measured, not guaranteed" and reporting per-content-type.

### B.4 Medium

**M1 — Summarizer recursion mitigation may break the summarizer.** §13 says the marker header is "rejected if seen twice." A summarizer request legitimately carries the marker once; the "reject if seen twice" rule needs a precise definition of what increments the count and what happens on a false positive. Prefer a hard rule: summarizer requests bypass the pipeline entirely via an internal call path, not by round-tripping through the public HTTP surface with a header clients could also set.

**M2 — Disk cap behavior is unspecified.** §6 sets a 5GB default cap with a 1GB warning, but §5.2's retention default is "keep forever." What happens at 5GB? Silent stop-capturing, oldest-eviction, or hard error? Specify the eviction/backpressure policy so memory capture degrades predictably rather than filling the disk or silently dropping writes.

**M3 — "Force model" override can silently break clients.** §5.1 lets a single configured model override the client's request. Clients that branch on the returned `model` field, or that sent a model-specific tool/schema, may misbehave. Recommend echoing the *requested* model back in the response envelope while routing to the forced model upstream, or at least documenting the observable divergence.

**M4 — Telemetry/privacy stance is unstated.** For a tool that captures every prompt, the absence of any statement about telemetry is itself a gap. Recommend an explicit "no outbound network calls except the configured upstream; no analytics; no phone-home" guarantee, since that is a primary reason a developer would self-host this.

**M5 — Schema/versioning across extensions.** §8.2's `extension_version` column is good, but there is no described upgrade path when an extension's schema changes between releases (forward migration, downgrade behavior, or refusal-to-start on schema mismatch). Specify the migration runner's contract, especially since imported claude-mem data (§11.2) will arrive at a specific schema version.

**M6 — MCP surface duplicates the memory API and needs a consistency rule.** Both `serve-mcp`/`serve` MCP tools and the `/memory/api/*` HTTP endpoints expose search. Confirm they share one query implementation (not two drifting ones) — this is exactly the kind of duplication that bites later. (claude-mem's own 3-layer MCP search pattern — search → timeline → get_observations for token efficiency — is worth porting deliberately rather than reinventing.)

### B.5 Low / editorial

- **L1** — §7.2.2 estimates claude-mem at "~30k LOC" and §7.2.3 cites headroom language percentages to one decimal. Pin these to a commit SHA and date, or soften to "approximately," since they will drift.
- **L2** — The default port is stated as `4242` (§9.1) but the launcher and collision-handling discussion never define the auto-increment or `--force` port-reuse behavior precisely. Cross-reference §8.5's pidfile handshake from §9.1.
- **L3** — `GET /v1/usage` returns HTML (§5.1) while everything else is JSON; confirm this is intentional (human dashboard) and not an inconsistency an API client will trip over.
- **L4** — Appendix A defines CCR as "Compressed Content Retrieval" but §5.3 and §11.3 use "reversible compression"/"CCR store" somewhat interchangeably; align the vocabulary.
- **L5** — The roadmap's week estimates (§14) imply ~11 weeks single-dev for a product spanning a protocol proxy, a memory store, and a compression engine with a Python sidecar. Realistic, but consider labeling phases by deliverable/gate rather than week count so slippage doesn't read as failure.

### B.6 Recommended additions before Phase 0

1. **A "Legal & TOS posture" section** (addresses C1) — the single most important missing piece.
2. **A Phase 0 license-verification gate** (addresses C2) with the vendored SHA + license recorded.
3. **A one-page threat model** covering the "hostile local process" case (addresses H4), even if the conclusion for several items is "accepted risk, single-user."
4. **A compression safety matrix** (addresses C3/H1): which content types are compressed by default, which are opt-in, which are never touched, and where in the message array memory is injected relative to the cache-stable prefix.
5. **A measured-baseline task in Phase 0** that records the imported proxy's real latency, so the §6 NFRs are calibrated to reality rather than aspiration (addresses H5).

### B.7 Things worth keeping exactly as they are

- The two invariants and the fail-open extension contract (§2, §8.3).
- The single-user scoping and its use as a complexity eliminator (§3.3).
- The "new repo, vendor-don't-submodule" decision (§7) — correct given the divergence argument.
- Bun + Hono + SQLite + TOML choices (§10) — coherent and appropriate for a single self-contained binary.
- The contract-test-corpus definition of "vanilla is a drop-in replacement" (§12) — this is the right acceptance gate and should be built first.
| Workstream | The developer's informal term for the combined activity across one or more sessions targeting a single goal; not a first-class concept in the data model, but supported via free-form session titles and cross-session search. |
| Upstream | The LLM provider CopilotMem forwards to (GitHub Copilot at launch). |
| Client | Any tool that sends requests to CopilotMem (Claude Code, Copilot CLI, Cursor, Codex, curl, custom scripts). Multiple clients can share one CopilotMem instance. |
