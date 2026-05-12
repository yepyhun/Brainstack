# Install And Profile Isolation

Brainstack is a Hermes memory plugin. It gives Hermes durable, inspectable,
token-efficient memory. It is not an orchestrator, scheduler, Kanban owner, or
company/workflow executor.

## Pieces

- `brainstack/`: the memory kernel plugin.
- `scripts/install_into_hermes.py`: the wizard that copies Brainstack into a
  Hermes checkout, patches supported Hermes seams, enables config, and can write
  profile-isolation paths.
- `scripts/brainstack_doctor.py`: checks that the active Hermes checkout and
  config match what Brainstack can actually run.
- `extensions/hermes_proactive/`: optional Hermes wake/pulse/surfacing runtime.
  It is not Brainstack core and does not install Evolver.

## Basic Install

Dry run:

```bash
python install_into_hermes.py /path/to/hermes-agent --enable --doctor --dry-run --runtime docker
```

Install:

```bash
python install_into_hermes.py /path/to/hermes-agent --enable --doctor --runtime docker
```

Local non-Docker:

```bash
python install_into_hermes.py /path/to/hermes-agent --enable --doctor --runtime local --embedding-runtime none
```

## Official Isolation Modes

### Shared Backend, Scoped Profiles

Use one Brainstack backend and let Brainstack isolate by principal/workspace
scope. This is for multiple Hermes profiles that may share one physical memory
backend safely.

```bash
python install_into_hermes.py /path/to/hermes-agent \
  --profile default \
  --enable \
  --isolate-brainstack \
  --isolation-mode shared-scoped \
  --doctor \
  --dry-run
```

### Full Home Isolation

Use a dedicated effective `HERMES_HOME` for the isolated profile. Brainstack and
the optional proactive extension both stay under that home:

```bash
python install_into_hermes.py /path/to/hermes-agent \
  --profile titans-agent \
  --enable \
  --isolate-brainstack \
  --isolation-mode full-home \
  --doctor
```

This writes the normal flat defaults:

```yaml
plugins:
  brainstack:
    db_path: "$HERMES_HOME/brainstack/brainstack.db"
    graph_backend: kuzu
    graph_db_path: "$HERMES_HOME/brainstack/brainstack.kuzu"
    corpus_backend: chroma
    corpus_db_path: "$HERMES_HOME/brainstack/brainstack.chroma"
extensions:
  hermes_proactive:
    state_base_dir: "$HERMES_HOME/home/brainstack"
```

Full-home mode is only truly full isolation if Hermes runs that profile with the
profile directory as its effective `HERMES_HOME`.

### Path-Override Isolation

Use one Hermes install/home but point Brainstack and proactive runtime state to
a profile-specific directory:

```bash
python install_into_hermes.py /path/to/hermes-agent \
  --profile titans-agent \
  --enable \
  --isolate-brainstack \
  --isolation-mode path-override \
  --doctor
```

The wizard writes flat Brainstack paths plus:

```yaml
extensions:
  hermes_proactive:
    state_base_dir: /path/to/profile/brainstack/proactive_runtime
```

## Unsupported Config Shape

Do not use this as an official Brainstack config:

```yaml
plugins:
  brainstack:
    stores:
      sqlite:
        db_path: /some/profile/brainstack.db
```

Those nested `stores.*` keys are not Brainstack runtime keys. The doctor now
reports them as ignored and tells you the supported flat replacement:

- `plugins.brainstack.db_path`
- `plugins.brainstack.graph_db_path`
- `plugins.brainstack.corpus_db_path`
- `extensions.hermes_proactive.state_base_dir`

## Verification

Run the doctor:

```bash
python scripts/brainstack_doctor.py /path/to/hermes-agent --config /path/to/config.yaml --runtime docker --check-docker
```

Run the multi-profile shared-backend verifier:

```bash
python scripts/verify_multi_profile_shared_backend.py
```

Run proactive extension checks:

```bash
python -m pytest -q tests/test_hermes_proactive_doctor_runtime.py
```

## Answer For The Common Question

If `default` and `coder` may share Brainstack but `titans-agent` must be fully
separate, do not copy a giant nested `stores.*` block by hand.

Use one of these:

- best: run `titans-agent` with a dedicated effective `HERMES_HOME`, then use
  `--profile titans-agent --isolate-brainstack --isolation-mode full-home`;
- or: use `--isolation-mode path-override`, which writes flat Brainstack paths
  and a proactive extension `state_base_dir` under the profile directory.

Afterward, run the doctor. If it reports ignored nested keys or shared proactive
runtime state, the profile is not fully isolated yet.
