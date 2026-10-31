# Dependency Index — ChatGPT package v3.25.2

This index documents the upstream resources that are referenced by the five active ChatGPT skills and their directly linked supporting materials. The complete original repository remains preserved separately and unchanged under `upstream/academic-research-skills-main/`.

## Package-relative mapping

All paths below are under this `skills/` directory. From an individual skill folder, use `../` before these paths. The mirrors are deliberately selective: only referenced files and the transitive Markdown-link targets required to make the packaged support set navigable are included here. The upstream snapshot contains the complete source tree.

| Upstream path | ChatGPT package path | Files | Purpose / handling |
|---|---|---:|---|
| `shared/` | `skills/shared/` | 147 | Shared protocols, handoff definitions, policy references, and JSON schemas cited by active skill material. |
| `docs/` | `skills/docs/` | 41 | Design specifications and operational documents referenced by skills or linked dependency documents. |
| `scripts/` | `skills/scripts/` | 132 | Selected Python/JS utilities, adapters, fixtures, and helpers explicitly referenced by skill source material. Source code only; do not claim execution unless a compatible runtime actually runs it. |
| `agents/` | `skills/agents/` | 1 | One upstream root-level role prompt referenced by screening material. Apply as an analytical perspective, not an independent agent. |
| `commands/` | `skills/commands/` | 1 | The referenced upstream command definition. Retained for traceability; it is not a ChatGPT slash command. |
| `evals/` | `skills/evals/` | 143 | Referenced gold and held-out fixtures for reviewer/claim-drift guidance. Fixtures are not run automatically. |
| `examples/` | `skills/examples/` | 25 | A referenced worked example and the `examples/pi/` set linked by supporting docs. Treat as examples, not factual evidence for a user's study. |
| `audits/`, `pi/`, `tests/` | Matching package paths | 3 | One linked audit record, one PI README, and one linked test calibration note. They provide context only; the test suite is not run automatically. |
| Root project documents | `skills/` | 6 | `GOVERNANCE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `THIRD_PARTY.md`, `POSITIONING.md`, and `LICENSE`, copied to resolve links from the selected support documents. |
| Each skill's own `agents/`, `references/`, `templates/`, `examples/` | Same skill folder | varies | Skill-specific source material retained alongside the adapted `SKILL.md`. Apply role prompts sequentially; do not present them as separately running agents. |
| Cross-skill folders such as `academic-paper/` and `deep-research/` | Sibling folders under `skills/` | varies | Shared handoffs and companion skill references. Use adapted ChatGPT workflow descriptions rather than legacy runtime commands. |

## Dependency handling rules

1. Resolve project-root-relative references such as `shared/...`, `docs/...`, or `scripts/...` to the matching path under `skills/`.
2. Resolve references such as `academic-paper/references/...` to the sibling skill folder `skills/academic-paper/...`.
3. Prefer the adapted ChatGPT `SKILL.md` for workflow behavior. Supporting agents, command files, hooks, scripts, and evaluation fixtures are reference/source assets unless the corresponding ChatGPT tool integration is explicitly available and used.
4. Never state that a script, hook, slash command, database connector, or independent agent ran merely because its source file is present.
5. When a cited file is outside this selected mirror, consult the preserved original snapshot under `upstream/academic-research-skills-main/` and disclose the limitation rather than inventing its contents.

## Integrity note

The **499 mirrored dependency files** were copied byte-for-byte from the supplied upstream v3.24.0 snapshot. The mirror is a navigable subset, not a second full clone; the original snapshot remains the source of record. Validation found **274 relative Markdown links and all resolved**, plus **215 project-relative path references in active skill files with no missing mirrors**. This stage repairs file availability and reference resolution only. It does not implement the MCP backend, script execution service, persistent state, or autonomous multi-agent orchestration.


## Stage 3 backend mapping (v3.25.3)
The deployable MCP source is in `backend/`. The selected deterministic Python source adapters are loaded from `skills/scripts/` and `skills/sr-screener/scripts/`. The server is stateless and uses temporary work directories. See `backend/README.md` for setup, tool schemas, resource limits, deployment constraints, and the unconnected status.
