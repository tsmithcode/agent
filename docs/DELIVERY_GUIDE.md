# CAD Guardian Delivery, Install, and Update Guide

This guide covers an end-to-end, repeatable release workflow with versioned artifacts and professional distribution.

## Goals

- Versioned releases with provenance
- One-line installs for customers
- Repeatable update path
- Optional Homebrew and private registry support

## Prerequisites (developer)

- GitHub repo with Actions enabled
- PyPI project created (name in `pyproject.toml`)
- Git tag versioning (`vX.Y.Z`)
- `OPENAI_API_KEY` set for runtime use (not required for build)

## 1) Developer Release Flow (recommended)

### A. Bump version

Update version in `pyproject.toml`.

### B. Commit and tag

```bash
git add pyproject.toml

git commit -m "release: vX.Y.Z"

git tag vX.Y.Z

git push origin main --tags
```

### C. GitHub Actions build + publish

The workflow `.github/workflows/release.yml` will:

- Run tests
- Build full wheel/sdist
- Build core profile wheel/sdist (`CG_BUILD_PROFILE=core`)
- Generate marketplace manifests
- Publish to PyPI for tagged releases

### D. Local profile builds (optional)

```bash
# full artifact (includes add-on modules)
python -m build

# core artifact (excludes cg.addons modules)
CG_BUILD_PROFILE=core python -m build --outdir dist-core
```

## 2) Customer Install (PyPI + pipx)

```bash
pipx install cad-guardian
cg setup
cg guide --mode starter
```

If you want dashboard dependencies installed at install time:

```bash
pipx install 'cad-guardian[dashboard]'
```

If `pipx` is not installed:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

## 3) Customer Update

```bash
pipx upgrade cad-guardian
```

If installed via venv:

```bash
pip install --upgrade cad-guardian
```

## 4) Uninstall

### pipx

```bash
pipx uninstall cad-guardian
```

### venv/pip

```bash
pip uninstall cad-guardian
```

### Homebrew

```bash
brew uninstall cad-guardian
```

## 5) Optional: Homebrew (macOS)

Formula lives at `packaging/homebrew/cad-guardian.rb`.

Update `url` + `sha256` per release tarball, then publish to your tap.

Install example:

```bash
brew tap your-org/cad-guardian
brew install cad-guardian
```

## 6) Enterprise / Private Registry (optional)

- Use GitHub Packages or Artifactory as a private Python registry.
- Update `pip` index URL for customers.
- This avoids public PyPI while keeping versioned installs.

## 7) Validation Checklist

Customer should run:

```bash
cg setup
cg doctor
cg do "show files"
```

## Notes

- Plugin config defaults to enabled, but command availability is contract-based (enabled in config + required files + required dependencies).
- Dashboard command appears only when dashboard plugin contract is satisfied (files + deps).
- Do not ship API keys. Customer sets `OPENAI_API_KEY` locally.
