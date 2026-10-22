#!/usr/bin/env python3
"""Download the official Godot 4.7.2 web template, then export Sakura Rally for Vercel."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

GODOT_VERSION = "4.7.2"
GODOT_VERSION_KEY = "4.7.2.stable"
USER_AGENT = "Mozilla/5.0 SakuraRallyWebBuild/1.0"
ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
CACHE = Path(os.environ.get("VERCEL_CACHE_DIR", ROOT / ".vercel" / "cache")) / f"godot-{GODOT_VERSION}"
ENGINE_URL = (
    "https://downloads.godotengine.org/?version=4.7.2&flavor=stable"
    "&slug=linux.x86_64.zip&platform=linux.64"
)
TEMPLATES_URL = (
    "https://downloads.godotengine.org/?version=4.7.2&flavor=stable"
    "&slug=export_templates.tpz&platform=templates"
)
WEB_TEMPLATE_MEMBER = "templates/web_nothreads_release.zip"


def open_url(url: str, headers: dict[str, str] | None = None):
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    return urllib.request.urlopen(request, timeout=180)


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    try:
        with open_url(url) as response, temporary.open("wb") as out:
            if response.status != 200:
                raise RuntimeError(f"Unexpected download status {response.status} for {url}")
            shutil.copyfileobj(response, out, 1024 * 1024)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


class RangeReader:
    """A seekable HTTP range reader, so only the requested member of the 1.28 GB TPZ is fetched."""

    def __init__(self, url: str, size: int) -> None:
        self.url = url
        self.size = size
        self.position = 0
        self.cache_start = -1
        self.cache = b""
        self.cache_size = 1024 * 1024

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            new_position = offset
        elif whence == io.SEEK_CUR:
            new_position = self.position + offset
        elif whence == io.SEEK_END:
            new_position = self.size + offset
        else:
            raise ValueError(f"Unknown seek mode: {whence}")
        if new_position < 0:
            raise ValueError("Cannot seek before the beginning of the archive")
        self.position = min(new_position, self.size)
        return self.position

    def read(self, count: int = -1) -> bytes:
        if count is None or count < 0:
            count = self.size - self.position
        count = min(count, self.size - self.position)
        if count <= 0:
            return b""

        end_position = self.position + count
        cache_end = self.cache_start + len(self.cache)
        if self.cache_start < 0 or self.position < self.cache_start or end_position > cache_end:
            self.cache_start = self.position
            range_end = min(self.size - 1, self.position + max(count, self.cache_size) - 1)
            with open_url(
                self.url,
                {"Range": f"bytes={self.position}-{range_end}"},
            ) as response:
                if response.status != 206:
                    raise RuntimeError(
                        "Godot template server did not honor byte ranges; refusing to download "
                        "the full export-template archive."
                    )
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith("bytes "):
                    raise RuntimeError("Godot template server returned no Content-Range header.")
                self.cache = response.read()
            if len(self.cache) < count:
                raise RuntimeError("Short range response while reading Godot export templates.")
        offset = self.position - self.cache_start
        result = self.cache[offset : offset + count]
        self.position += len(result)
        return result

    def close(self) -> None:
        return


def download_web_template(template_zip: Path) -> None:
    with open_url(TEMPLATES_URL, {"Range": "bytes=0-0"}) as response:
        if response.status != 206:
            raise RuntimeError("Godot export-template download does not support byte ranges.")
        content_range = response.headers.get("Content-Range", "")
    match = re.fullmatch(r"bytes 0-0/(\d+)", content_range.strip())
    if not match:
        raise RuntimeError(f"Could not determine Godot export-template size: {content_range!r}")
    total_size = int(match.group(1))

    with zipfile.ZipFile(RangeReader(TEMPLATES_URL, total_size)) as archive:
        try:
            template_info = archive.getinfo(WEB_TEMPLATE_MEMBER)
        except KeyError as error:
            raise RuntimeError(f"Official Godot package lacks {WEB_TEMPLATE_MEMBER}.") from error
        template_zip.parent.mkdir(parents=True, exist_ok=True)
        temporary = template_zip.with_suffix(template_zip.suffix + ".download")
        try:
            with archive.open(template_info) as source, temporary.open("wb") as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)
            if not zipfile.is_zipfile(temporary):
                raise RuntimeError("Downloaded web export template is not a valid ZIP archive.")
            temporary.replace(template_zip)
        finally:
            temporary.unlink(missing_ok=True)


def prepare_godot() -> tuple[Path, Path]:
    CACHE.mkdir(parents=True, exist_ok=True)
    executable = CACHE / "Godot_v4.7.2-stable_linux.x86_64"
    if not executable.exists():
        engine_zip = CACHE / "godot-linux-x86_64.zip"
        download_file(ENGINE_URL, engine_zip)
        with zipfile.ZipFile(engine_zip) as archive:
            try:
                member = archive.getinfo(executable.name)
            except KeyError as error:
                raise RuntimeError("Official Godot archive did not contain the Linux executable.") from error
            with archive.open(member) as source, executable.open("wb") as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)
        engine_zip.unlink(missing_ok=True)
        executable.chmod(executable.stat().st_mode | 0o111)

    home = CACHE / "home"
    templates_dir = home / ".local" / "share" / "godot" / "export_templates" / GODOT_VERSION_KEY
    template_zip = templates_dir / "web_nothreads_release.zip"
    if not template_zip.exists():
        download_web_template(template_zip)
    return executable, home


def main() -> int:
    if sys.platform != "linux" or os.uname().machine not in ("x86_64", "amd64"):
        raise RuntimeError("The automated web build currently requires a Linux x86_64 runner.")

    godot, home = prepare_godot()
    shutil.rmtree(PUBLIC, ignore_errors=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["XDG_DATA_HOME"] = str(home / ".local" / "share")
    environment.setdefault("GODOT_SILENCE_ROOT_WARNING", "1")

    command = [
        str(godot),
        "--headless",
        "--audio-driver",
        "Dummy",
        "--path",
        str(ROOT),
        "--export-release",
        "Web",
        str(PUBLIC / "index.html"),
    ]
    print(f"Exporting Sakura Rally for Web with Godot {GODOT_VERSION}…", flush=True)
    subprocess.run(command, cwd=ROOT, env=environment, check=True)

    html = PUBLIC / "index.html"
    if not html.is_file() or html.stat().st_size < 1024:
        raise RuntimeError("Godot export did not produce a valid public/index.html.")
    if not any(PUBLIC.glob("*.wasm")) or not any(PUBLIC.glob("*.pck")):
        raise RuntimeError("Godot export is missing the WebAssembly engine or game PCK.")
    with html.open("r", encoding="utf-8", errors="ignore") as page:
        beginning = page.read(4096).lower()
    if "godot" not in beginning:
        raise RuntimeError("Exported index.html does not appear to be a Godot game loader.")

    total_bytes = sum(file.stat().st_size for file in PUBLIC.rglob("*") if file.is_file())
    print(f"Exported game files: {len(list(PUBLIC.iterdir()))}; total {total_bytes:,} bytes", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Web export failed: {error}", file=sys.stderr)
        raise
