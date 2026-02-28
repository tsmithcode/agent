# Docs Versioning and Drift Policy

## Goal

Keep docs synchronized with shipping behavior on every release.

## Rules

1. Any command/flag/path change must include matching doc updates in the same PR.
2. Root `README.md` remains navigation-only (table of contents).
3. Canonical command syntax lives only in `docs/COMMAND_REFERENCE.md`.
4. Plugin behavior and gating rules live only in `docs/PLUGIN_ARCHITECTURE.md`.
5. Add-on operational details live in `core/cg/addons/README*.md`.

## Release Gate

Before tagging a release:

- Run docs QA checker (links + stale paths)
- Validate command list against current help output
- Confirm architecture docs still map to code folders

## Version Notes

For each release, include a docs changelog entry with:

- command surface changes
- plugin contract changes
- path/layout refactors affecting docs

## Ownership

- Engineering owns technical accuracy.
- Product/GTM owns positioning language in `docs/GTM_STRATEGY.md`.
