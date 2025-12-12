## Podman-HPC diagrams

This document provides a high-level, visual overview of how Podman-HPC works and the major tasks and code paths. Diagrams are written in Mermaid and render in many markdown viewers.

### 1) Architecture overview

```mermaid
flowchart LR
  subgraph user_space[User Space]
    U[User] --> CLI[podman-hpc CLI]
  end

  subgraph podhpc[Podman-HPC]
    CLI --> SC[SiteConfig]
    SC -->|read config YAML and templates and env| SC2[Config state]
    SC2 -->|compute default args and module args| Ext[get_cmd_extensions]
    CLI --> CP[call_podman or subcommands]
    Ext -->|inject default flags and hooks and env| CP
  end

  CP --> P[Podman]

  subgraph oci_hook[OCI Hook]
    P -- prestart when annotation podman_hpc.hook_tool=true --> HT[hook_tool]
    HT --> MD[modules.d YAML]
    HT -->|copy/bind actions| FS[(Container FS)]
    HT --> LDC[ldconfig]
  end

  P --> C[(Container lifecycle)]

  %% Other flows
  CLI --> MIG[migrate / rmsqi / pull]
  MIG --> MU[MigrateUtils]
  MU --> IS[(Image stores: overlay, layers, squash)]

  CLI --> SR[shared-run]
  SR --> MON[monitor process]
  SR --> RPROC[run process]
  RPROC --> P
  P --> EXEC[exec processes]
  EXEC --> C
  MON -->|wait all tasks then remove container| P
```

### 2) CLI command structure

```mermaid
flowchart TB
  A[podman-hpc] --> B[Default passthrough: call_podman]
  A --> C[infohpc]
  A --> D[migrate]
  A --> E[rmsqi]
  A --> F[pull]
  A --> G[shared-run]
  B -->|for any subcommand| P[Podman]
```

Key mappings:
- `call_podman`: wraps any `podman` subcommand and injects SiteConfig-derived flags.
- `infohpc`: prints version and resolved configuration.
- `migrate`: squashes an image into the squash store.
- `rmsqi`: removes a previously squashed image from the squash store.
- `pull`: pulls image via `podman`, then migrates on success.
- `shared-run`: starts one container per node and execs tasks into it.

### 3) Configuration precedence and environment setup

Source: `podman_hpc/siteconfig.py`

```mermaid
flowchart TB
  start([Start]) --> def[Built-in defaults]
  def --> cfchk{Config file exists?}
  cfchk -- yes --> read[Read config yaml]
  cfchk -- no --> envchk{Env overrides?}
  read --> tmpl["Template expansion (template keys)"]
  tmpl --> envchk
  envchk -- yes --> envset["Apply PODMANHPC_* env vars"]
  envchk -- no --> finalize[Finalize config attributes]
  envset --> finalize
  finalize --> mods["read_site_modules()"]
  mods --> args["Compute default_args + default_*_args"]
  args --> env["config_env(hpc=True): set XDG_CONFIG_HOME, drop XDG_RUNTIME_DIR"]
  env --> done([Config ready])
```

Notable outputs:
- Default flags for `run`, `build`, `pull`, `images`.
- Hooks enabled: `--hooks-dir`, `--annotation podman_hpc.hook_tool=true`, and `--env PODMANHPC_MODULES_DIR=...`.
- `additionalimagestore`: includes squash dir and optional stores.

### 4) OCI hook execution sequence

Source: `podman_hpc/configure_hooks.py`, `podman_hpc/hook_tool.py`

```mermaid
sequenceDiagram
  participant Podman
  participant Hook as hook_tool (prestart)
  participant Mods as modules.d (YAML)
  participant FS as Container FS

  Podman->>Hook: Invoke prestart hook (annotation=true)
  Hook->>Hook: read config.json, merge env, read modules.d
  Hook->>Hook: setns(pid, mnt)
  Hook->>Hook: chroot(/)
  Hook->>Mods: load module defs (copy/bind rules, env keys)
  loop for each module enabled via env
    Hook->>FS: perform copy/bind per rule (resolve src/dest with globs)
  end
  Hook->>Hook: chroot(root_path)
  Hook->>FS: ldconfig
  Hook-->>Podman: return (continue container init)
```

Module YAML keys used by hook:
- `name`, `env` (enable via env var)
- `copy`: file/dir copy rules
- `bind`: bind-mount rules

### 5) shared-run workflow (per node)

Source: `podman_hpc/podman_hpc.py::_shared_run`

```mermaid
sequenceDiagram
  participant User
  participant PH as podman-hpc
  participant Mon as monitor(Process)
  participant Run as shared_run_exec(Process)
  participant Podman
  participant Cont as Container

  User->>PH: podman-hpc shared-run [options] IMAGE CMD...
  PH->>PH: parse options and filter valid run/exec flags
  PH->>Mon: start monitor(sock, ntasks, container_name)
  PH->>Run: start run process (podman run --rm -d --name ...)
  PH->>Podman: wait until container exists + running (poll with backoff)
  Note over PH: compute wait_poll_interval / wait_timeout based on ntasks
  PH->>Podman: podman exec ... CMD (PMI_FD handled if present)
  Podman->>Cont: execute user command(s)
  PH->>Mon: send_complete(socket, localid)
  Mon->>Podman: kill container and remove container
  PH-->>User: exit with exec return code
```

PMI handling:
- If `PMI_FD` is set, dup to fd 3 and pass via `--preserve-fds 1`.

### 6) Migrate-to-scratch workflow

Source: `podman_hpc/migrate2scratch.py`

```mermaid
flowchart TB
  start(["migrate image"]) --> init[_lazy_init - resolve src-dst stores]
  init --> refresh[initialize dst storage then refresh src and dst]
  refresh --> info{image found?}
  info -- no --> abort[[return False]]
  info -- yes --> layers[get image layers]
  layers --> dup{dst has image id?}
  dup -- yes --> done[[previously migrated return True]]
  dup -- no --> dtag[drop image tags]
  dtag --> copyi[copy image info]
  copyi --> copyl[copy required layers]
  copyl --> overlay[copy overlay data]
  overlay --> squash[generate squash file]
  squash -- fail --> abort2[[return False]]
  squash -- ok --> record[add image record]
  record --> done[[return True]]
```

### 7) Module processing during command extension

Source: `podman_hpc/siteconfig.py::get_cmd_extensions`

```mermaid
flowchart TB
  start([Start get_cmd_extensions]) --> base[cmds = default_args]
  base --> subcmd{subcommand?}
  subcmd -- run --> runA[+ default_run_args]
  subcmd -- build --> buildA[+ default_build_args]
  subcmd -- pull --> pullA[+ default_pull_args]
  subcmd -- images --> imgsA[+ default_images_args]
  subcmd -- other --> noop[no-op]
  runA --> pick
  buildA --> pick
  pullA --> pick
  imgsA --> pick
  noop --> pick
  pick[Identify enabled modules from parsed CLI flags]
  pick --> deps[Warn if required deps not enabled]
  deps --> conf[Warn on conflicts]
  conf --> ext[Append module additional_args; set env; set shared_run flag]
  ext --> loglvl{log_level set?}
  loglvl -- yes --> plus[+ --log-level LEVEL]
  loglvl -- no --> out
  plus --> out([Return cmds])
  out --> endNode([End])
```

Enabled module logic:
- A module is enabled when its `cli_arg` flag is present for the subcommand.
- Adds `additional_args`, sets `-e <ENV>=1`, and may set `shared_run=True`.
- Warnings are printed for missing `depends_on` and conflicting modules.

---

References:
- CLI and shared-run: `podman_hpc/podman_hpc.py`
- Config: `podman_hpc/siteconfig.py`
- Hook configuration: `podman_hpc/configure_hooks.py`
- Hook runtime: `podman_hpc/hook_tool.py`
- Migration utilities: `podman_hpc/migrate2scratch.py`


