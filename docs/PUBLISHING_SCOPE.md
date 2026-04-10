# Publishing Scope

This repository is a focused Brainstack plugin snapshot, not the entire Hermes codebase.

Important limits:

- Brainstack is currently designed for direct Hermes integration.
- Some modules and tests expect Hermes runtime interfaces.
- Donor refresh is bounded and honest, not fully automatic.
- External embedding services are not baseline dependencies for the current Brainstack implementation.
- The repository now includes an install/update/doctor kit for applying Brainstack into a fresh Hermes checkout, but that kit still assumes Hermes-native provider integration rather than a standalone API deployment.
- The integration kit now supports both Docker and local Hermes runtime modes through one shared installer/doctor flow; runtime mode changes verification behavior, not Brainstack ownership.
