from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import unescape
from pathlib import Path


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DRIVE_FOLDER_TYPE = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class FetchResult:
    downloaded_files: int
    partial: bool
    partial_reason: str


def _extract_folder_id(url: str) -> str:
    m = re.search(r"/drive/folders/([A-Za-z0-9_-]+)", url or "")
    if not m:
        raise ValueError("Could not parse Google Drive folder id from link.")
    return m.group(1)


def _build_opener() -> urllib.request.OpenerDirector:
    cj = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cj)
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def _parse_drive_entries(page_html: str) -> list[tuple[str, str, str]]:
    encoded_data = None
    for script in re.finditer(r"<script[^>]*>(.*?)</script>", page_html, flags=re.DOTALL | re.IGNORECASE):
        inner = script.group(1)
        if "_DRIVE_ivd" not in inner:
            continue
        matches = list(re.finditer(r"'((?:[^'\\]|\\.)*)'", inner))
        if len(matches) >= 2:
            encoded_data = matches[1].group(1)
            break
    if encoded_data is None:
        raise RuntimeError("Unable to parse Google Drive folder page. Check sharing permissions.")

    decoded = encoded_data.encode("utf-8").decode("unicode_escape")
    folder_arr = json.loads(decoded)
    folder_contents = [] if folder_arr[0] is None else folder_arr[0]
    entries: list[tuple[str, str, str]] = []
    for e in folder_contents:
        fid = str(e[0])
        name = str(e[2]).encode("raw_unicode_escape").decode("utf-8")
        ftype = str(e[3])
        entries.append((fid, name, ftype))
    return entries


def _download_file(opener: urllib.request.OpenerDirector, file_id: str, out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    base = f"https://drive.google.com/uc?export=download&id={urllib.parse.quote(file_id)}"
    req = urllib.request.Request(base, headers={"User-Agent": USER_AGENT})
    with opener.open(req, timeout=60) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        content_disposition = (resp.headers.get("Content-Disposition") or "").lower()
        body = resp.read()

    if "attachment" in content_disposition or not content_type.startswith("text/html"):
        out_file.write_bytes(body)
        return

    html = body.decode("utf-8", errors="ignore")
    token_match = (
        re.search(r"confirm=([0-9A-Za-z_]+)", html)
        or re.search(r'name="confirm" value="([0-9A-Za-z_]+)"', html)
    )
    if not token_match:
        raise RuntimeError(f"Failed to resolve direct download token for file id={file_id}")
    token = token_match.group(1)
    confirm_url = (
        "https://drive.google.com/uc?export=download"
        f"&confirm={urllib.parse.quote(token)}&id={urllib.parse.quote(file_id)}"
    )
    req2 = urllib.request.Request(confirm_url, headers={"User-Agent": USER_AGENT})
    with opener.open(req2, timeout=120) as resp2:
        out_file.write_bytes(resp2.read())


def download_public_folder(url: str, output: Path) -> FetchResult:
    folder_id = _extract_folder_id(url)
    opener = _build_opener()
    root = output.resolve()
    root.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    partial = False
    partial_reason = ""

    stack: list[tuple[str, Path]] = [(folder_id, root)]
    while stack:
        cur_id, cur_dir = stack.pop()
        cur_url = f"https://drive.google.com/drive/folders/{urllib.parse.quote(cur_id)}?hl=en"
        req = urllib.request.Request(cur_url, headers={"User-Agent": USER_AGENT})
        with opener.open(req, timeout=60) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        entries = _parse_drive_entries(html)
        if len(entries) >= 50:
            partial = True
            partial_reason = (
                "Google Drive UI may cap listing at ~50 entries per folder view without API/OAuth; "
                "downloaded files may be partial for very large folders."
            )

        for file_id, file_name, file_type in entries:
            safe_name = unescape(file_name).replace("/", "_").replace("\\", "_")
            if file_type == DRIVE_FOLDER_TYPE:
                sub_dir = cur_dir / safe_name
                sub_dir.mkdir(parents=True, exist_ok=True)
                stack.append((file_id, sub_dir))
            else:
                _download_file(opener, file_id, cur_dir / safe_name)
                downloaded += 1

    return FetchResult(downloaded_files=downloaded, partial=partial, partial_reason=partial_reason)
