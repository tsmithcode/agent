# Architecture (Core + Plugin Lifecycle)

## Core Runtime Architecture

```mermaid
flowchart TD
    U[User CLI Input] --> M[core/cg/cli/main.py]
    M --> R{Mode}
    R -->|ask| ASK[core/cg/runtime/ask_engine.py]
    R -->|run/do| RUN[core/cg/runtime/run_engine.py]

    RUN --> ROUTE[core/cg/routing/router.py]
    ROUTE -->|deterministic| TOOLS[core/cg/routing/tool_registry.py]
    ROUTE -->|llm| LLM[core/cg/runtime/llm.py]

    RUN --> EXEC[core/cg/safety/executor.py]
    RUN --> POLICY[core/cg/safety/policy.py]
    ASK --> POLICY

    RUN --> MEM[core/cg/data/memory.py]
    ASK --> MEM

    RUN --> TEL[core/cg/observability/telemetry.py]
    ASK --> TEL
    M --> DOC[core/cg/observability/doctor.py]
```

## Plugin Lifecycle Architecture

```mermaid
flowchart TD
    CFG[config/plugins.json] --> RESOLVE[core/cg/safety/plugins.py::resolve_plugins]
    CONTRACTS[plugin contracts] --> RESOLVE
    RESOLVE --> MANIFEST[core/cg/safety/capability_manifest.py]
    MANIFEST --> CLIREG[core/cg/cli/main.py + command_groups.py]

    CLIREG -->|enabled| SURFACE[Command exposed in help + runtime]
    CLIREG -->|disabled| HIDE[Command hidden]

    SURFACE --> ADDON[core/cg/addons/*]
    ADDON --> TEL[Telemetry + Reports]

    DOC[docs/PLUGIN_ARCHITECTURE.md] --> DEV[Extension workflow]
```

## Separation of Concerns

- `cli/`: command surfaces and user interaction flow
- `runtime/`: ask/run engines and model orchestration
- `routing/`: deterministic scoring and route decisions
- `safety/`: policy, executor, plugin contracts, capability manifest
- `data/`: memory, paths, env loading
- `observability/`: telemetry and diagnostics
- `addons/`: optional plugin implementations
