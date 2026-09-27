#!/usr/bin/env python3
"""Render a PDF page-by-page and package it for Kindle with Kindle Comic Converter."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


PROFILES = {
    "kindle-11": ("K11", "Kindle 11 (1072 × 1448)"),
    "paperwhite-1-2": ("KPW", "Kindle Paperwhite 1/2 (758 × 1024)"),
    "paperwhite-3-4": ("KPW34", "Kindle Paperwhite 3/4 (1072 × 1448)"),
    "paperwhite-5": ("KPW5", "Kindle Paperwhite 5/Signature (1236 × 1648)"),
    "oasis": ("KO", "Kindle Oasis 2/3 (1264 × 1680)"),
    "voyage": ("KV", "Kindle Voyage (1072 × 1448)"),
    "scribe": ("KS", "Kindle Scribe 1/2 (1860 × 2480)"),
    "basic-older": ("K57", "Kindle 5/7, including 7th-gen basic Kindle (600 × 800)"),
}


def executable(
    name: str,
    override: str | None = None,
    option: str | None = None,
    label: str | None = None,
) -> str:
    candidate = override or name
    resolved = shutil.which(candidate)
    if not resolved:
        option = option or name
        raise RuntimeError(
            f"Could not find '{candidate}'. Install {label or name} or pass its path with --{option}."
        )
    return resolved


def page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.jpg$", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def pdf_page_count(pdf: Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return None
    result = subprocess.run([pdfinfo, str(pdf)], capture_output=True, text=True, check=False)
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    return int(match.group(1)) if result.returncode == 0 and match else None


def progress_spinner(label: str, stop: threading.Event) -> None:
    frames = "|/-\\"
    started = time.monotonic()
    frame = 0
    while not stop.wait(0.25):
        elapsed = int(time.monotonic() - started)
        sys.stderr.write(f"\r{frames[frame % len(frames)]} {label} ({elapsed}s elapsed)   ")
        sys.stderr.flush()
        frame += 1
    sys.stderr.write(f"\r✓ {label} ({int(time.monotonic() - started)}s)                    \n")
    sys.stderr.flush()


def render_pages(pdf: Path, destination: Path, pdftoppm: str, dpi: int) -> int:
    raw_dir = destination / "rendered"
    pages_dir = destination / "pages"
    raw_dir.mkdir()
    pages_dir.mkdir()
    prefix = raw_dir / "page"
    total_pages = pdf_page_count(pdf)
    with tempfile.TemporaryFile(mode="w+t") as error_log:
        process = subprocess.Popen(
            [pdftoppm, "-jpeg", "-jpegopt", "quality=95", "-r", str(dpi), str(pdf), str(prefix)],
            stdout=subprocess.DEVNULL,
            stderr=error_log,
            text=True,
        )
        started = time.monotonic()
        last_count = -1
        try:
            while process.poll() is None:
                count = len(list(raw_dir.glob("page-*.jpg")))
                if count != last_count:
                    if total_pages:
                        percent = min(100, round(count * 100 / total_pages))
                        status = f"Rendering pages: {count}/{total_pages} ({percent}%)"
                    else:
                        status = f"Rendering pages: {count} rendered"
                    sys.stderr.write(f"\r{status} ({int(time.monotonic() - started)}s elapsed)   ")
                    sys.stderr.flush()
                    last_count = count
                time.sleep(0.4)
        except KeyboardInterrupt:
            process.terminate()
            process.wait()
            sys.stderr.write("\n")
            raise
        error_log.seek(0)
        error_output = error_log.read()
    if total_pages:
        status = f"Rendered {len(list(raw_dir.glob('page-*.jpg')))}/{total_pages} pages"
    else:
        status = f"Rendered {len(list(raw_dir.glob('page-*.jpg')))} pages"
    sys.stderr.write(f"\r✓ {status} ({int(time.monotonic() - started)}s)                    \n")
    sys.stderr.flush()
    if process.returncode:
        detail = error_output.strip()
        suffix = f": {detail}" if detail else "."
        raise RuntimeError(f"PDF rendering failed (pdftoppm exited with {process.returncode}){suffix}")
    rendered = sorted(raw_dir.glob("page-*.jpg"), key=page_number)
    if not rendered:
        raise RuntimeError("No pages were rendered. Check that the PDF is readable and not password-protected.")
    for index, page in enumerate(rendered, start=1):
        page.rename(pages_dir / f"page-{index:06d}.jpg")
    return len(rendered)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2kindle",
        description="Turn every PDF page into a fixed visual page in a Kindle-compatible book.",
        epilog="The output is a single .mobi file containing KCC's dual MOBI/AZW3 Kindle format.",
    )
    parser.add_argument("pdf", type=Path, nargs="?", help="Input PDF")
    parser.add_argument(
        "-p", "--profile", choices=PROFILES, default="basic-older",
        help="Kindle screen preset (default: basic-older)",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output file (default: PDF folder/name.mobi)")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render resolution (default: 300)")
    parser.add_argument("--manga", action="store_true", help="Enable right-to-left manga reading mode")
    parser.add_argument("--title", help="Book title metadata (default: PDF filename)")
    parser.add_argument("--author", help="Author metadata")
    parser.add_argument("--force", action="store_true", help="Replace the output file if it already exists")
    parser.add_argument("--kcc", help="Path to KCC's kcc-c2e executable")
    parser.add_argument("--pdftoppm", help="Path to Poppler's pdftoppm executable")
    parser.add_argument("--list-profiles", action="store_true", help="List supported Kindle screen presets and exit")
    return parser


def convert(args: argparse.Namespace) -> Path:
    if args.pdf is None:
        raise RuntimeError("Provide an input PDF.")
    source = args.pdf.expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise RuntimeError(f"PDF not found: {source}")
    if source.suffix.lower() != ".pdf":
        raise RuntimeError("Input must be a .pdf file.")
    if source.stat().st_size == 0:
        raise RuntimeError("Input PDF is empty.")
    with source.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise RuntimeError("Input does not have a valid PDF header.")
    if args.dpi < 72 or args.dpi > 1200:
        raise RuntimeError("--dpi must be between 72 and 1200.")

    output = (args.output.expanduser() if args.output else source.with_suffix(".mobi")).resolve()
    if output.suffix.lower() != ".mobi":
        raise RuntimeError("KCC's Kindle fixed-layout output must use the .mobi extension.")
    if output == source:
        raise RuntimeError("Output path must differ from the input PDF.")
    if output.exists() and not args.force:
        raise RuntimeError(f"Output already exists: {output} (use --force to replace it)")

    renderer = executable("pdftoppm", args.pdftoppm)
    kcc = executable(
        "kcc-c2e", args.kcc, "kcc", "Kindle Comic Converter's command-line tool (KCC)"
    )
    profile, profile_label = PROFILES[args.profile]
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdf2kindle-") as working:
        work = Path(working)
        pages_dir = work / "pages"
        count = render_pages(source, work, renderer, args.dpi)
        print(f"Rendered {count} pages at {args.dpi} DPI.", file=sys.stderr)
        print(f"Applying {profile_label} profile…", file=sys.stderr)

        kcc_output = work / "book.mobi"
        command = [kcc, "-p", profile, "-f", "MOBI", "-q", "-c", "0", "-t", args.title or source.stem]
        if args.author:
            command.extend(["-a", args.author])
        if args.manga:
            command.append("-m")
        command.extend(["-o", str(kcc_output), str(pages_dir)])
        stop_progress = threading.Event()
        spinner = threading.Thread(
            target=progress_spinner,
            args=("KCC optimizing and packaging", stop_progress),
            daemon=True,
        )
        spinner.start()
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        finally:
            stop_progress.set()
            spinner.join()
        if result.returncode:
            if result.stdout:
                print(result.stdout, file=sys.stderr, end="")
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            output_log = f"{result.stdout}\n{result.stderr}".lower()
            if "kindlegen is missing" in output_log:
                raise RuntimeError(
                    "KCC needs KindleGen for MOBI output. On Arch, install the AUR package with "
                    "'yay -S kindlegen', then confirm 'command -v kindlegen' finds it."
                )
            raise RuntimeError(
                f"KCC conversion failed (exit code {result.returncode}). Check KCC and KindleGen installation."
            )
        if not kcc_output.is_file():
            candidates = list(work.rglob("*.mobi"))
            if len(candidates) != 1:
                raise RuntimeError("KCC finished but did not produce one identifiable .mobi output file.")
            kcc_output = candidates[0]
        if kcc_output.stat().st_size == 0:
            raise RuntimeError("KCC produced an empty output file.")

        # Stage alongside the destination so replacement is atomic on the same filesystem.
        staged = output.with_name(f".{output.stem}.pdf2kindle-{os.getpid()}.mobi")
        try:
            shutil.copy2(kcc_output, staged)
            os.replace(staged, output)
        finally:
            staged.unlink(missing_ok=True)
    return output


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.list_profiles:
        for key, (code, label) in PROFILES.items():
            print(f"{key:18} {label} [{code}]")
        return 0
    try:
        output = convert(args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"pdf2kindle: error: {error}", file=sys.stderr)
        return 1
    print(f"Created: {output}")
    print("KCC's .mobi file contains both legacy MOBI and AZW3-compatible fixed-layout content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
