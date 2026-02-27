# Marketplace Manifest Packaging

This folder contains marketplace metadata for CAD Guardian distribution.

## Files

- `app-manifest.json`: source-of-truth app manifest
- `build_release_manifest.py`: build-time generator for release manifests
- `dist/app-manifest.json`: generated copy of base manifest (CI output)
- `dist/app-manifest.release.json`: generated release manifest with artifact checksums (CI output)

## Local generation

```bash
cd /home/cg-ai/agent
python -m build
python packaging/marketplace/build_release_manifest.py --release-ref "local-build"
```

## CI integration

`/.github/workflows/release.yml` runs manifest generation after package build and uploads JSON manifests as workflow artifacts.
