# CAD Guardian GTM Strategy

## Product Category

CAD Guardian is a **local-first AI agent CLI platform** for power users who need:

- live workspace understanding
- policy-controlled action execution
- auditable telemetry for enterprise reporting

## Ideal Customer Profile (ICP)

- Solo technical operators
- Engineering leads managing automation risk
- Teams that need policy controls before broad AI rollout

## Core Value Promise

- One CLI for insight (`ask`) and action (`run`, `do`)
- Deterministic-first routing for obvious tasks
- Policy controls for cost, runtime, and safety boundaries
- Plugin-based expansion for reporting, evals, and ingestion

## Packaging Strategy

### Core Distribution (default)

- Target: broad adoption, fastest install
- Includes: core CLI, policy engine, deterministic routing, telemetry logging
- Excludes optional add-on surfaces when plugin contracts are unmet

### Full Distribution (`[full]` extras)

- Target: advanced users and enterprise pilots
- Adds dependencies for dashboard and related tooling
- Unlocks complete plugin experience when contracts validate

## Revenue Motion (Practical)

1. **Land** with core CLI value (`cg ask`, `cg do`, `cg doctor`)
2. **Expand** with add-ons (dashboard, eval, metrics)
3. **Scale** with policy profiles + telemetry exports for decision makers

## Feature-to-Offer Packaging

| Offer | What customer gets | Why it sells |
|---|---|---|
| Starter | Core CLI + policy tiers + doctor | Fast proof of value |
| Pro | Starter + metrics + snapshots + eval | Team-level confidence and QA |
| Enterprise | Pro + dashboard + deployment runbook + custom policy baselines | Governance, reporting, rollout safety |

## Marketplace Positioning

Title:
- CAD Guardian - Policy-Controlled AI CLI Platform

Short description:
- Ask over a live runtime snapshot and run policy-controlled actions from one CLI.

Differentiators to emphasize:
- deterministic-first behavior
- plugin contracts
- telemetry for BI/reporting
- low-friction install/update path

## Adoption KPIs

Track these first:

- time-to-first-successful-command
- command success rate
- deterministic route share vs LLM share
- repeat usage per user/session
- policy tier adoption (`cheap/base/max`)

## Documentation-to-GTM Rules

- Root README stays navigation-only
- GTM language lives only in this file + marketplace manifest
- Plugin technical detail lives only in `PLUGIN_ARCHITECTURE.md`
