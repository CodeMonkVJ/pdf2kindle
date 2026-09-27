# pdf2kindle

Convert a PDF into a fixed-page Kindle book. Each PDF page is rasterized as a full-page JPEG first, so selectable text becomes page artwork and slides, diagrams, comic panels, and mixed layouts keep their original positions.

```sh
pdf2kindle book.pdf
```

The result is written beside the PDF as `book.mobi`. Kindle Comic Converter (KCC) produces a single dual-format Kindle file with both legacy MOBI and AZW3-compatible fixed-layout content. KCC uses the `.mobi` extension for this file; it does not create a standalone `.azw3` file.

## Requirements

- Python 3.10 or newer
- Poppler's `pdftoppm` command
- Kindle Comic Converter's command-line tool `kcc-c2e` (the KCC GUI alone is not enough)
- KindleGen available to KCC for MOBI output (KCC may bundle or detect it depending on how KCC is installed)

On Arch Linux, install Poppler with `sudo pacman -S poppler`, KCC's CLI from the AUR (for example, `yay -S kcc`), and KindleGen with `yay -S kindlegen`. KindleGen is an optional KCC dependency required for MOBI output. On other systems, install KCC, Poppler, and KindleGen using their project instructions. See KCC's [KindleGen installation notes](https://github.com/ciromattia/kcc/wiki/Installation#kindlegen).

Then create a project-local virtual environment and install this command from the project directory:

```sh
python -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/pdf2kindle book.pdf
```

To use the shorter `pdf2kindle` command in future terminals, activate the environment first with `source .venv/bin/activate`.

If the tools are not on `PATH`, pass their executable paths with `--pdftoppm` and `--kcc`.

Check that the KCC command is available with `command -v kcc-c2e`. If it is installed under another path, provide it with `--kcc /path/to/kcc-c2e`.

## Kindle profiles

The default profile is `basic-older`, which matches the 7th-generation basic Kindle's 600 × 800 screen. To see all available presets:

```sh
pdf2kindle --list-profiles
```

Choose a profile explicitly when needed:

```sh
pdf2kindle book.pdf --profile scribe
```

Available presets include Kindle 11, Paperwhite 1/2, Paperwhite 3/4, Paperwhite 5, Oasis 2/3, Voyage, Scribe 1/2, and older basic Kindles. The selected device profile controls KCC's page resizing. Choose `--profile paperwhite-5` to use the previous default for a Paperwhite 5 / Signature Edition.

## Options

```text
pdf2kindle INPUT.pdf [--profile PROFILE] [--output FILE.mobi]
                      [--dpi 300] [--manga] [--title TITLE]
                      [--author AUTHOR] [--force]
```

- `--dpi`: PDF rasterization resolution; defaults to 300.
- `--manga`: enable right-to-left manga reading order.
- `--output`: choose a different output location. It must have a `.mobi` extension.
- `--force`: replace an existing output file.
- `--title`, `--author`: set book metadata.

Whitespace cropping is disabled by default to preserve page edges and layout-sensitive content. KCC still resizes each page to the chosen Kindle profile. Conversion work files are temporary and removed when the command finishes.

The command reports rendered-page progress as a count and percentage, then shows a live elapsed-time indicator while KCC optimizes and packages the book. KCC does not expose a dependable percentage for that final phase, so the indicator shows activity and elapsed time instead.

## Limitations

Every page is an image in the resulting book. Text selection, dictionary lookup, font resizing, and sentence-level search/highlighting are not available. Higher DPI can increase conversion time and output size. Password-protected PDFs are not supported.
