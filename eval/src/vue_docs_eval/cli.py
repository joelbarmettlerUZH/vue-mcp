"""Typer CLI for the evaluation suite."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from vue_docs_eval.questions import generate_questions
from vue_docs_eval.reports import format_comparison_report, format_single_report, save_report
from vue_docs_eval.runner import load_questions, run_evaluation

app = typer.Typer(name="vue-docs-eval", help="Evaluation suite for Vue ecosystem docs MCP")
console = Console()

EVAL_DIR = Path("eval")


def _configure_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def _build_providers(names: list[str]) -> list:
    """Instantiate provider objects from names."""
    providers = []
    for name in names:
        if name == "ours":
            from vue_docs_eval.providers.ours import OursProvider

            providers.append(OursProvider())
        elif name == "context7":
            from vue_docs_eval.providers.context7 import Context7Provider

            providers.append(Context7Provider())
        else:
            raise typer.BadParameter(f"Unknown provider: {name}. Available: ours, context7")
    return providers


@app.command()
def run(
    providers: Annotated[
        str, typer.Option(help="Comma-separated providers (ours, context7)")
    ] = "ours",
    frameworks: Annotated[
        str, typer.Option(help="Comma-separated frameworks (vue, vue-router)")
    ] = "vue",
    max_questions: Annotated[int | None, typer.Option(help="Limit number of questions")] = None,
    max_results: Annotated[int, typer.Option(help="Max search results per query")] = 10,
    judge_model: Annotated[str | None, typer.Option(help="Gemini model for judging")] = None,
    judge_runs: Annotated[int, typer.Option(help="Judge runs per question for median")] = 1,
    output: Annotated[Path, typer.Option(help="Output directory")] = EVAL_DIR / "results",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
):
    """Run evaluation against one or more providers."""
    _configure_logging(verbose)

    provider_list = _build_providers([p.strip() for p in providers.split(",")])
    framework_list = [f.strip() for f in frameworks.split(",")]
    question_paths = [EVAL_DIR / "questions" / f"{fw}.json" for fw in framework_list]
    questions = load_questions(question_paths)

    if max_questions:
        questions = questions[:max_questions]
        console.print(f"[bold]Limited to {len(questions)} questions[/bold]")

    console.print(
        f"[bold]Running eval:[/bold] {len(questions)} questions, "
        f"providers={providers}, frameworks={frameworks}"
    )

    report = asyncio.run(
        run_evaluation(
            providers=provider_list,
            questions=questions,
            judge_model=judge_model,
            judge_runs=judge_runs,
            max_results=max_results,
        )
    )

    # Print report
    if len(report.providers) > 1:
        text = format_comparison_report(report)
    elif report.providers:
        text = format_single_report(report.providers[0])
    else:
        text = "No results."
    console.print(text)

    # Save
    json_path, report_path = save_report(report, output, report.timestamp)
    console.print(f"\n[green]Results saved:[/green] {json_path}")
    console.print(f"[green]Report saved:[/green] {report_path}")


@app.command()
def generate(
    framework: Annotated[str, typer.Option(help="Framework name (e.g. vue, vue-router)")],
    docs_path: Annotated[Path, typer.Option(help="Path to documentation source")],
    count: Annotated[int, typer.Option(help="Number of questions to generate")] = 50,
    model: Annotated[str | None, typer.Option(help="Gemini model to use")] = None,
    output: Annotated[Path | None, typer.Option(help="Output file path")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
):
    """Generate evaluation questions for a framework."""
    _configure_logging(verbose)

    console.print(f"[bold]Generating {count} questions for {framework}...[/bold]")

    questions = generate_questions(
        framework=framework,
        docs_path=docs_path,
        count=count,
        model=model,
    )

    out_path = output or EVAL_DIR / "questions" / f"{framework}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(questions, f, indent=2)

    console.print(f"[green]Wrote {len(questions)} questions to {out_path}[/green]")
