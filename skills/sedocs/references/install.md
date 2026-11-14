# Installing sedocs

The skills drive a command-line tool named `sedocs`. Check it first:

```
sedocs doctor
```

If the command is not found, install it with uv (https://docs.astral.sh/uv/):

```
uv tool install git+https://github.com/VicDario/sedocs-ai
```

From a local clone of the repository:

```
uv tool install /path/to/sedocs-ai
```

Without installing, any command can be run as `uvx --from git+https://github.com/VicDario/sedocs-ai sedocs <command>`.

## Optional system tools

`sedocs doctor` lists what is present. Nothing here is required to validate a model or to write SVG diagrams.

| Tool | Needed for | Debian or Ubuntu | macOS (Homebrew) |
|------|-----------|------------------|------------------|
| librsvg (`rsvg-convert`) | PNG diagrams and diagrams inside documents | `apt install librsvg2-bin` | `brew install librsvg` |
| LibreOffice (`soffice`) | `sedocs preview` | `apt install libreoffice-writer` | `brew install --cask libreoffice` |
| poppler (`pdftoppm`) | page images in the preview | `apt install poppler-utils` | `brew install poppler` |

Inkscape or ImageMagick can replace librsvg. Ask the user before installing system packages.
