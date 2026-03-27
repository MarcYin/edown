# Manifest

Each run writes a JSON manifest that captures:

- the effective configuration
- discovered images and their native grid metadata
- alignment groups
- download outcomes
- stack outcomes

This makes it possible to re-run stacking without repeating search, and to inspect skipped or failed images programmatically.

When `edown stack` updates the manifest, it also records the stack-run configuration under `stack_config`.
