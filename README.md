# CopilotMem

A single self-hosted local proxy for AI coding assistants. Sits between your IDE / CLI / script and GitHub Copilot; adds opt-in cross-session memory and prompt compression as pluggable middleware. Vanilla pass-through always available.

**Status**: Phase 0 — repository bootstrapping. Not yet functional.

## Documentation

- **Product Requirements Document**: [`docs/PRD.md`](docs/PRD.md) — read this first. Defines scope, architecture, and design decisions.
- **Architecture**: `docs/ARCHITECTURE.md` — coming in Phase 0 completion.
- **Extensions**: `docs/EXTENSIONS.md` — coming in Phase 1.
- **Migration guide**: `docs/MIGRATION.md` — coming in Phase 1.

## Quick reference

| Item | Value |
|---|---|
| Default HTTP port | `4242` |
| State directory (Windows) | `%LOCALAPPDATA%\copilotmem\` |
| State directory (Unix) | `~/.local/share/copilotmem/` |
| Config file | `<state>/config.toml` |
| Database | `<state>/copilotmem.db` |
| Env var prefix | `COPILOTMEM_*` |

Full namespace mapping and coexistence guarantees with existing tools (`copilot-api`, `claude-mem`) are documented in PRD §7.5.

## Source projects

CopilotMem consolidates capabilities from three upstream projects:

| Source | Strategy | Location |
|---|---|---|
| [`ericc-ch/copilot-api`](https://github.com/ericc-ch/copilot-api) | Git submodule | `vendor/copilot-api/` |
| [`thedotmack/claude-mem`](https://github.com/thedotmack/claude-mem) | Ported to TypeScript | `src/extensions/memory/` |
| [`prajoria/headroom`](https://github.com/prajoria/headroom) | Ported to TypeScript | `src/extensions/compress/` |

Rationale for each choice is in PRD §7.2.

## Contributor setup

After cloning, install the in-repo git hooks so commits are checked against the issue-first workflow (see [`SESSION-START.md`](SESSION-START.md) §8.5):

```bash
./scripts/install-hooks.sh          # Linux / macOS / Git Bash
```

```powershell
.\scripts\install-hooks.ps1         # Windows PowerShell 7+
```

Both scripts are idempotent and only set `git config core.hooksPath .githooks` in this clone.

## License

Apache License 2.0. See `LICENSE`.

Ported and adapted code carries attribution headers referencing the upstream commit SHA it was derived from.
