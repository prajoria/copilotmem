# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

**Phase 0 — repository bootstrapping.** Only `README.md`, `LICENSE`, `docs/PRD.md`, and the `vendor/copilot-api` submodule exist. There is no `src/`, no `package.json`, no test runner, and no build script yet. Do **not** invent commands or file paths that aren't here — read `docs/PRD.md` first and check whether the thing you need still has to be scaffolded.

## Source of truth

**`docs/PRD.md` (v0.4) is the design contract.** Every architectural question — layout, ports, state paths, extension model, coexistence rules, roadmap — is answered there. When in doubt, cite the PRD section (e.g. "per §7.5") in commits/PRs rather than paraphrasing.

Key sections to know by number:
- **§5** functional requirements (core proxy vs. memory vs. compression extensions)
- **§7.3** the target repo layout (`src/core/`, `src/extensions/{memory,compress,cache-align,tos-rate-limit}/`, `src/pipeline/`, `src/cli/`, `src/shared/`, `src/migrations/`, `tests/{contract,coexistence,integration,unit}/`)
- **§7.5** the definitive namespace table — ports, state dirs, env-var prefix, token filenames — that must not collide with `copilot-api` or `claude-mem`
- **§8.1** the fixed 9-stage request pipeline
- **§8.3** the `ProxyExtension` / `RequestContext` / `ResponseContext` interface
- **§10** locked design decisions (Bun runtime, Hono HTTP, HTMX viewer, TOML config, Apache-2.0)
- **§14** phased roadmap

## Vendored upstream

`vendor/copilot-api/` is a **git submodule** pointing at `prajoria/copilot-api` (see `.gitmodules`). After a fresh clone:

```bash
git submodule update --init --recursive
```

Treat submodule contents as read-only vendor code. The proxy's own routes/translation/upstream/auth live under `src/core/` as **thin adapters** into the submodule (§7.2.1). Bumping the submodule is done via `scripts/bump-copilot-api.ts` once that script exists.

The other two source projects (`claude-mem`, `headroom`) are **ported to TypeScript in-tree** under `src/extensions/memory/` and `src/extensions/compress/`, with per-file attribution headers citing the upstream commit SHA — they are not submodules (§7.2.2, §7.2.3).

## Non-negotiable invariants

These come from PRD §2 and §7.5. Any change that violates them is wrong regardless of how clean the diff looks.

1. **Vanilla always works.** With every extension disabled or crashed, the proxy must be byte-identical to a bare Copilot-to-Anthropic/OpenAI translator. This is enforced by `tests/contract/`.
2. **Extensions fail open.** A thrown exception, timeout, or misconfig in any stage is caught by the pipeline runner, logged with the request ID, and the request continues as if that stage were disabled. Never let an extension bubble errors to the client.
3. **Namespace separation from existing tools.** CopilotMem must touch **no** port, file, directory, or env var used by `copilot-api` or `claude-mem`. Defaults are locked to:
   - Port `4242`
   - Windows state: `%LOCALAPPDATA%\copilotmem\` — Unix state: `~/.local/share/copilotmem/`
   - DB: `<state>/copilotmem.db`; config: `<state>/config.toml`; token: `<state>/upstream_token`; PID: `<state>/copilotmem.pid`
   - Env prefix: `COPILOTMEM_*`
   - Placeholder API key value: `copilotmem-proxy`
   
   `tests/coexistence/` will assert that CopilotMem on `:4242` runs alongside `copilot-api` on `:4141` and `claude-mem`'s worker on `:37777` with zero collisions.
4. **Bind to `127.0.0.1` by default.** Any other bind requires an explicit `--bind` flag and emits a warning; the product is single-user, single-workstation (§3.3).

## Request pipeline shape (§8.1)

Every request flows through this fixed order; extension stages may be skipped, core stages may not:

1. Ingress translation (core) → 2. TOS rate-limit (core default) → 3. Memory injection (ext) → 4. Compression (ext) → 5. Cache-prefix alignment (ext) → 6. Upstream call (core) → 7. Response capture to memory, async off request path (ext) → 8. Decompression / retrieval-token handling (ext) → 9. Egress translation (core)

Per-request headers override config (§9.4): `X-CopilotMem-Session`, `X-CopilotMem-Project`, `X-CopilotMem-Extensions: -compress,-memory` (or `none` for vanilla).

## Data model (§8.2)

One SQLite file, one connection pool. Core owns `requests`, `sessions`, `projects`. Each extension owns its own tables via migrations under `src/migrations/`, and every table carries an `extension_version` column so extensions can migrate independently.

## Repo commands

Nothing to build/test/lint yet — Phase 0 hasn't produced `package.json`. When those land they will be Bun-based (`bun install`, `bun test`, `bun build --compile`, per §10.1). Until then:

- `git submodule update --init --recursive` — required after clone
- Read `docs/PRD.md` before writing scaffold code so the layout in §7.3 is followed exactly

## Style notes for ported code

Files in `src/extensions/memory/` and `src/extensions/compress/` must carry an attribution header naming the upstream project and the specific commit SHA they were derived from (per README "Ported and adapted code" note and §7.2). Don't strip these headers when refactoring.

## What this repo is not (§3.3)

Multi-user, team memory sharing, hosted deployment, multi-tenant proxying, a coding assistant itself, a universal LLM router, or a fine-tuning/observability platform. Feature requests that pull in any of those directions should be pushed back with a pointer to §3.3.
