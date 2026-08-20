# Politeia-ds import notes

- Imported on: 2026-08-18
- Source: `/Users/one/Library/CloudStorage/OneDrive-个人/oneresearch/Politeia-ds`
- Purpose: preserve the pre-AutoResearcher research corpus without overwriting
  the framework or the active flat research scaffold.

## Included (research-content documents only)

- Research proposal, research/development plans, code guide, and project layout
- `docs/` and `wiki/` knowledge bases
- `research/physics-validation/` plans, notes, state, and reflection records

## Excluded

- All simulator source code, CMake files, and build scripts
  (`src/`, `CMakeLists.txt`, `scripts/`)
- All run configurations and operational data
  (`*.cfg`, `*.sh` under `research/physics-validation/jobs/`, `servers.toml`)
- The older AutoResearcher copy: `AGENTS.md`, `autoresearcher.md`, `workflow/`,
  `rules/`, `pyproject.toml`, and `src/autoresearcher/`
- Editor configuration, caches, egg-info, build directories, and OS metadata

The imported `research/physics-validation/plan.json` is retained verbatim. It is
not valid JSON in its current source form and has not been promoted to the active
`research/plan.json`. Adapting it to the current flat-plan schema should be a
separate, reviewed migration step.
