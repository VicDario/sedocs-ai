"""Command line of sedocs-ai.

    sedocs init [DIR]                 starter project model and document spec
    sedocs check MODEL                validate a project model
    sedocs render usecase|context MODEL -o FILE.svg|.png
    sedocs build SPEC [-o FILE.docx]  build a Word document
    sedocs preview FILE.docx          PDF and page images of a document
    sedocs inspect FILE.docx          structure and loose ends of a document
    sedocs doctor                     which external tools are installed
"""
from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from .context import render_context_diagram
from .docinfo import inspect_docx
from .doctor import check as doctor_check
from .document import BuildError, build_document
from .model import ModelError, has_errors, load_project, validate
from .preview import PreviewError, preview
from .raster import RenderToolMissing, svg_to_png
from .usecase import DiagramError, render_use_case_diagram


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sedocs", description="Software engineering documents from a single project model.")
    parser.add_argument("--version", action="version", version=f"sedocs-ai {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write a starter project.yaml and document.yaml")
    init.add_argument("directory", nargs="?", default=".")
    init.add_argument("--lang", choices=("en", "es"), default="en", help="output language of the documents")
    init.add_argument("--force", action="store_true", help="overwrite existing files")

    check = commands.add_parser("check", help="validate a project model")
    check.add_argument("model")
    check.add_argument("--strict", action="store_true", help="treat warnings as errors")

    render = commands.add_parser("render", help="draw a diagram of the model")
    render.add_argument("diagram", choices=("usecase", "context"))
    render.add_argument("model")
    render.add_argument("-o", "--output", required=True, help="output file, .svg or .png")
    render.add_argument("--module", help="draw the use cases of this module")
    render.add_argument("--use-cases", help="comma-separated use case ids to draw")
    render.add_argument("--diagram-id", help="use the options of this entry of 'diagrams' in the model")
    render.add_argument("--title", help="label of the system boundary (or of the system in a context diagram)")
    render.add_argument("--show-ids", action="store_true", help="write the id above the name of each use case")
    render.add_argument("--no-neighbors", action="store_true", help="leave out related use cases of other modules")
    render.add_argument("--width", type=int, default=2400, help="pixel width of the PNG (default 2400)")

    build = commands.add_parser("build", help="build a Word document from a document spec")
    build.add_argument("spec")
    build.add_argument("-o", "--output", help="output .docx (default: out/<spec name>.docx next to the spec)")

    prev = commands.add_parser("preview", help="render a .docx to PDF and page images")
    prev.add_argument("document")
    prev.add_argument("--out-dir", help="folder for the PDF and the images (default: .sedocs/preview next to the file)")
    prev.add_argument("--dpi", type=int, default=80)
    prev.add_argument("--no-images", action="store_true", help="only the PDF")

    insp = commands.add_parser("inspect", help="show the structure and the loose ends of a .docx")
    insp.add_argument("document")

    commands.add_parser("doctor", help="report which external tools are installed")
    return parser


def _init(args) -> int:
    target = Path(args.directory)
    target.mkdir(parents=True, exist_ok=True)
    templates = resources.files("sedocs_ai") / "templates"
    written = []
    for name in ("project.yaml", "document.yaml"):
        destination = target / name
        if destination.exists() and not args.force:
            print(f"error: {destination} already exists (use --force to overwrite)", file=sys.stderr)
            return 1
        text = (templates / name).read_text(encoding="utf-8").replace("language: en", f"language: {args.lang}")
        destination.write_text(text, encoding="utf-8")
        written.append(str(destination))
    print("created " + " and ".join(written))
    print("next: fill in the model, then run 'sedocs check project.yaml' and 'sedocs build document.yaml'")
    return 0


def _check(args) -> int:
    project = load_project(args.model)
    issues = validate(project)
    for issue in issues:
        print(issue)
    errors = sum(issue.level == "error" for issue in issues)
    warnings = len(issues) - errors
    print(f"{project.name or args.model}: {len(project.use_cases)} use cases, {len(project.functional)} functional and "
          f"{len(project.non_functional)} non-functional requirements; {errors} errors, {warnings} warnings")
    return 1 if errors or (args.strict and warnings) else 0


def _render(args) -> int:
    project = load_project(args.model)
    if has_errors(validate(project)):
        print("error: the model has errors; run 'sedocs check' first", file=sys.stderr)
        return 1
    output = Path(args.output)
    if output.suffix.lower() not in (".svg", ".png"):
        print("error: the output file must end in .svg or .png", file=sys.stderr)
        return 1
    warnings: list[str] = []
    if args.diagram == "context":
        svg = render_context_diagram(project, args.title)
    else:
        options: dict = {}
        if args.diagram_id:
            options = next((dict(d) for d in project.diagrams if str(d.get("id")) == args.diagram_id), None)
            if options is None:
                raise DiagramError(f"diagram '{args.diagram_id}' is not defined under 'diagrams' in the model")
            options.pop("id", None)
            options.pop("type", None)
        if args.module:
            options["module"] = args.module
        if args.use_cases:
            options["use_cases"] = [item.strip() for item in args.use_cases.split(",") if item.strip()]
        if args.title:
            options["title"] = args.title
        if args.show_ids:
            options["show_ids"] = True
        if args.no_neighbors:
            options["neighbors"] = False
        svg, warnings = render_use_case_diagram(project, **options)
    output.parent.mkdir(parents=True, exist_ok=True)
    svg_path = output.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    if output.suffix.lower() == ".png":
        svg_to_png(svg_path, output, args.width)
    for warning in warnings:
        print("WARNING " + warning)
    if warnings:
        print("hint: move the use case with 'positions' in a 'diagrams' entry of the model, then render again")
    print(f"wrote {output}")
    return 0


def _build(args) -> int:
    report = build_document(args.spec, args.output)
    for warning in report.warnings:
        print("WARNING " + warning)
    print(f"wrote {report.output}: {report.tables} tables, {report.figures} figures, {len(report.cited)} sources cited")
    return 0


def _preview(args) -> int:
    pdf, pages = preview(args.document, args.out_dir, args.dpi, images=not args.no_images)
    print(f"wrote {pdf}")
    for page in pages:
        print(f"page  {page}")
    return 0


def _inspect(args) -> int:
    info = inspect_docx(args.document)
    print(f"title: {info['title']}\nauthor: {info['author']}")
    print(f"tables: {info['tables']}  figures: {info['figures']}  citations: {len(info['cited'])}  sources: {len(info['sources'])}")
    print("headings:")
    for level, text in info["headings"]:
        print("  " * level + text)
    print("captions:")
    for caption in info["captions"]:
        print(f"  [{caption['position']}] {caption['text']}")
    for problem in info["problems"]:
        print("PROBLEM " + problem)
    return 1 if info["problems"] else 0


def _doctor(args) -> int:
    lines, ok = doctor_check()
    print("\n".join(lines))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handler = {"init": _init, "check": _check, "render": _render, "build": _build, "preview": _preview,
               "inspect": _inspect, "doctor": _doctor}[args.command]
    try:
        return handler(args)
    except (ModelError, DiagramError, BuildError, PreviewError, RenderToolMissing) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
