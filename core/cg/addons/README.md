# Add-ons Overview

This directory contains optional plugin implementations.

## Add-ons

- [Dashboard Add-on](README.dashboard.md)
- [Eval Harness Add-on](README.eval.md)
- [Drive Fetch Add-on](README.fetch_drive.md)

Canonical command syntax:

- [`docs/COMMAND_REFERENCE.md`](../../../docs/COMMAND_REFERENCE.md)

## Design Intent

- Keep core CLI reliable without add-ons
- Isolate optional dependencies in add-on modules
- Make contracts explicit through `core/cg/safety/plugins.py`

## Contract Linkage

Each add-on must match:

- plugin key in `config/plugins.json`
- contract entry in `core/cg/safety/plugins.py`
- command registration path in `core/cg/cli/command_groups.py`
