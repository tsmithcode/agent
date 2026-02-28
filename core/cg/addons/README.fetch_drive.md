# Drive Fetch Add-on

## Purpose

Downloads public Google Drive folders into workspace in a predictable structure for downstream agent workflows.

## Commands

- `cg fetch "<drive-folder-link>" --folder <name>`
- optional: `-d`, `--open/--no-open`

Authoritative command reference:

- [`docs/COMMAND_REFERENCE.md`](../../../docs/COMMAND_REFERENCE.md)

## Files

- `gdrive_fetch.py`: Drive listing and file download logic

## Inputs

- Google Drive folder URL
- target folder name

## Outputs

- downloaded files in `workspace/downloads/<folder>-<timestamp>`
- folder summary output in CLI

## Notes

- Command should clearly indicate partial-download risks for very large folders.
- Output path is the primary handoff for batch workflows.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| only partial files downloaded | very large or complex Drive folder structure | split source into smaller subfolders and rerun |
| command missing | plugin gated off | enable `fetch_drive` plugin and verify with `cg doctor` |
| invalid link error | non-folder or unsupported URL format | use a public Google Drive folder link |
| no output folder opened | headless/SSH environment | use printed destination path directly |
