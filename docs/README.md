# CAD Guardian Documentation Map

This folder is the single index for product, GTM, architecture, delivery, and design docs.

## Document Ownership (No Overlap)

| Document | Owns | Does Not Repeat |
|---|---|---|
| `../README.md` | Top-level table of contents only | Deep install, architecture, plugin details |
| `COMMAND_REFERENCE.md` | Canonical commands/flags and routing examples | Release process or GTM copy |
| `GTM_STRATEGY.md` | Positioning, ICP, packaging strategy, revenue motion | Runtime internals and command reference |
| `PLUGIN_ARCHITECTURE.md` | Plugin contracts, runtime gating, build profiles | GTM narrative and release operations |
| `ARCHITECTURE.md` | Minimal runtime and plugin lifecycle diagrams | Command syntax details |
| `DOCS_VERSIONING_POLICY.md` | Anti-drift rules and release docs gate | UX design/style rules |
| `DELIVERY_GUIDE.md` | Release, install, update, uninstall runbooks | Product positioning and plugin internals |
| `TELEMETRY_SCHEMA.md` | Event/report schema for analytics | UX copy and deployment process |
| `BRAND_DESIGN_GUIDE.md` | Brand consistency rules | Runtime logic and plugin behavior |
| `CLI_COLOR_RULES.md` | Terminal color semantics | Dashboard theming internals |
| `../core/cg/addons/README*.md` | Add-on behavior and inputs/outputs | Core architecture and GTM strategy |

## Recommended Reading Paths

- Founder / GTM lead:
  1. `GTM_STRATEGY.md`
  2. `DELIVERY_GUIDE.md`
  3. `../packaging/marketplace/app-manifest.json`

- Platform engineer:
  1. `COMMAND_REFERENCE.md`
  2. `PLUGIN_ARCHITECTURE.md`
  3. `ARCHITECTURE.md`
  4. `TELEMETRY_SCHEMA.md`
  5. `../core/cg/addons/README.md`

- Customer success / onboarding:
  1. `DELIVERY_GUIDE.md`
  2. `BRAND_DESIGN_GUIDE.md`

## Direct Links

- [GTM Strategy](GTM_STRATEGY.md)
- [Command Reference](COMMAND_REFERENCE.md)
- [Plugin Architecture](PLUGIN_ARCHITECTURE.md)
- [Architecture Diagrams](ARCHITECTURE.md)
- [Docs Versioning Policy](DOCS_VERSIONING_POLICY.md)
- [Delivery Guide](DELIVERY_GUIDE.md)
- [Telemetry Schema](TELEMETRY_SCHEMA.md)
- [Brand and Design Guide](BRAND_DESIGN_GUIDE.md)
- [CLI Color Rules](CLI_COLOR_RULES.md)
- [Add-ons Overview](../core/cg/addons/README.md)
- [Add-on: Dashboard](../core/cg/addons/README.dashboard.md)
- [Add-on: Eval Harness](../core/cg/addons/README.eval.md)
- [Add-on: Drive Fetch](../core/cg/addons/README.fetch_drive.md)
