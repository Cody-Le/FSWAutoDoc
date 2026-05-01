"""
Space FSW Simulation — MCP Documentation Server
------------------------------------------------
Tools exposed to Claude:

  READ
    list_docs()
    get_doc(filename)

  GENERIC EDIT (works on ANY .tex file)
    str_replace_in_doc(filename, old, new)
    create_doc(filename, title, subtitle, body)

  DECISIONS LOG
    add_architecture_decision(id, decision, rationale, alternatives)
    add_strategic_decision(id, decision, rationale, notes)
    add_open_question(id, question, context)
    resolve_open_question(id, resolution)

  ROADMAP
    update_roadmap_item_status(search_text, new_status)
    update_roadmap_phase_status(phase_title, new_status)
    append_roadmap_item(phase_title, subsection_title, item_text, status)

  BUILD + VCS
    compile_doc(filename)
    compile_all()
    git_commit_push(message)

  BRANCH
    get_current_branch()
    list_branches()
    switch_branch(branch_name)
    create_branch(branch_name, switch_to)

Transport:
  Local:    MCP_TRANSPORT=stdio  python server.py
  Deployed: MCP_TRANSPORT=sse    python server.py
"""

import os
import re
import subprocess
import datetime
from pathlib import Path
from fastmcp import FastMCP

# ── Config ────────────────────────────────────────────────────────────────────

DOCS_DIR = Path(os.environ.get("DOCS_DIR", "./docs")).resolve()
API_KEY  = os.environ.get("API_KEY", "")

mcp = FastMCP("space-fsw-docs", dependencies=["fastmcp"])


# ── Base preamble template ────────────────────────────────────────────────────
# Shared across all docs. create_doc() stitches this with caller-supplied body.
# Uses double-braces for literal LaTeX braces (Python .format() escaping).

_PREAMBLE = r"""
\documentclass[11pt, letterpaper]{{article}}

% ── Packages ──────────────────────────────────────────────
\usepackage[margin=1in]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{titlesec}}
\usepackage{{enumitem}}
\usepackage{{tabularx}}
\usepackage{{booktabs}}
\usepackage{{colortbl}}
\usepackage{{xcolor}}
\usepackage{{hyperref}}
\usepackage{{fancyhdr}}
\usepackage{{parskip}}
\usepackage{{microtype}}

% ── Colors ────────────────────────────────────────────────
\definecolor{{navy}}{{HTML}}{{1B3A5C}}
\definecolor{{midblue}}{{HTML}}{{2E5984}}
\definecolor{{lightblue}}{{HTML}}{{D5E8F0}}
\definecolor{{rowalt}}{{HTML}}{{F2F7FB}}
\definecolor{{gray500}}{{HTML}}{{888888}}
\definecolor{{gray300}}{{HTML}}{{CCCCCC}}
\definecolor{{green}}{{HTML}}{{2D6A4F}}
\definecolor{{amber}}{{HTML}}{{B45309}}

% ── Fonts ─────────────────────────────────────────────────
\setmainfont{{DejaVu Sans}}
\setsansfont{{DejaVu Sans}}
\setmonofont{{DejaVu Sans Mono}}

% ── Hyperlinks ────────────────────────────────────────────
\hypersetup{{colorlinks=true, linkcolor=midblue, urlcolor=midblue}}

% ── Header / Footer ──────────────────────────────────────
\pagestyle{{fancy}}
\fancyhf{{}}
\setlength{{\headheight}}{{22pt}}
\addtolength{{\topmargin}}{{-10pt}}
\renewcommand{{\headrulewidth}}{{0.8pt}}
\renewcommand{{\headrule}}{{\hbox to\headwidth{{\color{{navy}}\leaders\hrule height \headrulewidth\hfill}}}}
\fancyhead[R]{{\small\textcolor{{navy}}{{\textbf{{Space FSW Simulation}}}} \textcolor{{gray500}}{{| {header_label}}}}}
\fancyfoot[C]{{\small\textcolor{{gray500}}{{DRAFT --- {month_year} \quad|\quad Page \thepage}}}}

% ── Section Styling ───────────────────────────────────────
\titleformat{{\section}}
  {{\Large\bfseries\color{{navy}}}}
  {{\thesection}}{{1em}}{{}}
\titlespacing*{{\section}}{{0pt}}{{1.5em}}{{0.8em}}

\titleformat{{\subsection}}
  {{\large\bfseries\color{{midblue}}}}
  {{\thesubsection}}{{1em}}{{}}
\titlespacing*{{\subsection}}{{0pt}}{{1.2em}}{{0.5em}}

% ── Table Helpers ─────────────────────────────────────────
\newcommand{{\tableheader}}[1]{{\textbf{{\textcolor{{white}}{{#1}}}}}}
\renewcommand{{\arraystretch}}{{1.4}}
\setlength{{\tabcolsep}}{{8pt}}

% ── Status Tags ──────────────────────────────────────────
\newcommand{{\done}}{{\textcolor{{green}}{{\textbf{{[DONE]}}}}}}
\newcommand{{\inprog}}{{\textcolor{{amber}}{{\textbf{{[IN PROGRESS]}}}}}}
\newcommand{{\planned}}{{\textcolor{{gray500}}{{\textbf{{[PLANNED]}}}}}}
"""

_DOC_WRAPPER = r"""
\begin{{document}}
\thispagestyle{{empty}}

% ── Title Block ───────────────────────────────────────────
\begin{{flushleft}}
{{\fontsize{{32}}{{36}}\selectfont\bfseries\color{{navy}} {title}}}\\[6pt]
{{\fontsize{{18}}{{22}}\selectfont\color{{midblue}} {subtitle}}}\\[8pt]
{{\color{{gray300}}\rule{{\textwidth}}{{1.5pt}}}}\\[4pt]
{{\small\color{{gray500}} Living document\quad|\quad {month_year}\quad|\quad Space FSW Simulation}}
\end{{flushleft}}
\vspace{{1.5em}}

{body}

\end{{document}}
"""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _doc_path(filename: str) -> Path:
    """Resolve, validate, and return an absolute path inside DOCS_DIR."""
    path = (DOCS_DIR / filename).resolve()
    if not str(path).startswith(str(DOCS_DIR)):
        raise ValueError(f"Path traversal blocked: {filename}")
    if path.suffix != ".tex":
        raise ValueError(f"Only .tex files are supported: {filename}")
    return path


def _require_exists(filename: str) -> Path:
    path = _doc_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filename}")
    return path


def _read(filename: str) -> str:
    return _require_exists(filename).read_text(encoding="utf-8")


def _write(filename: str, content: str) -> None:
    _doc_path(filename).write_text(content, encoding="utf-8")


def _str_replace(filename: str, old: str, new: str) -> None:
    content = _read(filename)
    count = content.count(old)
    if count == 0:
        raise ValueError(f"Target string not found in {filename}:\n{old[:120]!r}")
    if count > 1:
        raise ValueError(
            f"Target string is ambiguous ({count} matches) in {filename}. "
            "Make the search string more specific."
        )
    _write(filename, content.replace(old, new, 1))


def _compile(filename: str) -> str:
    """Two xelatex passes. Returns 'ok' or last 40 log lines on error."""
    path = _require_exists(filename)
    cmd = ["xelatex", "-interaction=nonstopmode", path.name]
    result = None
    for _ in range(2):
        result = subprocess.run(cmd, cwd=str(DOCS_DIR), capture_output=True, text=True)
    if result.returncode != 0:
        lines = (result.stdout + result.stderr).splitlines()
        return "ERROR:\n" + "\n".join(lines[-40:])
    return "ok"


def _today() -> str:
    return datetime.date.today().strftime("%b %Y")


def _validate_status(status: str) -> None:
    valid = {"done", "inprog", "planned"}
    if status not in valid:
        raise ValueError(f"status must be one of {valid}, got: {status!r}")


# ── READ tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_docs() -> str:
    """
    List all .tex files currently in DOCS_DIR.
    Call this at the start of a session to see what exists.
    """
    files = sorted(DOCS_DIR.glob("*.tex"))
    if not files:
        return "No .tex files found in DOCS_DIR."
    return "\n".join(f.name for f in files)


@mcp.tool()
def get_doc(filename: str) -> str:
    """
    Return the full source of a .tex documentation file.
    Valid files: architecture_overview.tex, decisions_log.tex,
    technical_roadmap.tex, editing_procedure.tex, system_diagram.tex,
    or any file returned by list_docs().
    """
    return _read(filename)


# ── GENERIC EDIT tools ────────────────────────────────────────────────────────

@mcp.tool()
def str_replace_in_doc(filename: str, old: str, new: str) -> str:
    """
    Surgical str_replace on any .tex file.
    old must appear EXACTLY ONCE in the file — make it long enough to be unambiguous.

    Works on any file: architecture_overview.tex, system_diagram.tex,
    technical_roadmap.tex, decisions_log.tex, editing_procedure.tex, or new docs.

    Use this for:
      - Updating the Current Status section in architecture_overview.tex
      - Editing TikZ node labels or coordinates in system_diagram.tex
      - Any one-off change that does not have a dedicated tool
    """
    _str_replace(filename, old, new)
    return f"str_replace applied to {filename}."


@mcp.tool()
def create_doc(filename: str, title: str, subtitle: str, body: str) -> str:
    """
    Create a new .tex documentation file using the shared project preamble.
    The preamble (colors, fonts, header/footer, section styling, status tags)
    is injected automatically — do NOT include \\documentclass or preamble in body.

    filename: e.g. 'comm_flow.tex'
    title:    large heading e.g. 'Communication Flow'
    subtitle: smaller subheading e.g. 'TCP IPC protocol and packet structure'
    body:     LaTeX content that goes after the title block

    Will refuse to overwrite an existing file.
    """
    path = _doc_path(filename)
    if path.exists():
        raise FileExistsError(
            f"{filename} already exists. Use str_replace_in_doc to edit it."
        )

    month_year   = _today()
    header_label = title if len(title) <= 30 else title[:27] + "..."

    preamble = _PREAMBLE.format(header_label=header_label, month_year=month_year)
    wrapper  = _DOC_WRAPPER.format(
        title=title, subtitle=subtitle, month_year=month_year, body=body
    )
    _write(filename, preamble + wrapper)
    return f"Created {filename}."


# ── DECISIONS LOG tools ───────────────────────────────────────────────────────

@mcp.tool()
def add_architecture_decision(
    id: str,
    decision: str,
    rationale: str,
    alternatives: str,
) -> str:
    """
    Append a new row to the Architecture Decisions table in decisions_log.tex.
    id:           e.g. 'D014'
    decision:     short description of what was decided
    rationale:    why this decision was made
    alternatives: what else was considered
    """
    row = (
        f"  {id} & {_today()} &\n"
        f"    {decision} &\n"
        f"    {rationale} &\n"
        f"    {alternatives} \\\\\n"
        "  % -- INSERT NEW ARCHITECTURE DECISIONS ABOVE THIS LINE --"
    )
    _str_replace(
        "decisions_log.tex",
        "% -- INSERT NEW ARCHITECTURE DECISIONS ABOVE THIS LINE --",
        row,
    )
    return f"Added architecture decision {id}."


@mcp.tool()
def add_strategic_decision(
    id: str,
    decision: str,
    rationale: str,
    notes: str,
) -> str:
    """
    Append a new row to the Strategic Decisions table in decisions_log.tex.
    id: e.g. 'S004'
    """
    row = (
        f"  {id} & {_today()} &\n"
        f"    {decision} &\n"
        f"    {rationale} &\n"
        f"    {notes} \\\\\n"
        "  % -- INSERT NEW STRATEGIC DECISIONS ABOVE THIS LINE --"
    )
    _str_replace(
        "decisions_log.tex",
        "% -- INSERT NEW STRATEGIC DECISIONS ABOVE THIS LINE --",
        row,
    )
    return f"Added strategic decision {id}."


@mcp.tool()
def add_open_question(id: str, question: str, context: str) -> str:
    """
    Append a new row to the Open Questions table in decisions_log.tex.
    id: e.g. 'Q006'
    """
    row = (
        f"  {id} &\n"
        f"    {question} &\n"
        f"    {context} \\\\\n"
        "  % -- INSERT NEW OPEN QUESTIONS ABOVE THIS LINE --"
    )
    _str_replace(
        "decisions_log.tex",
        "% -- INSERT NEW OPEN QUESTIONS ABOVE THIS LINE --",
        row,
    )
    return f"Added open question {id}."


@mcp.tool()
def resolve_open_question(id: str, resolution: str) -> str:
    """
    Mark an open question resolved in decisions_log.tex.
    Prepends [RESOLVED --- <date>] and appends the resolution summary.
    id:         e.g. 'Q005'
    resolution: one-sentence summary of how it was resolved
    """
    content = _read("decisions_log.tex")
    pattern = re.compile(
        rf"({re.escape(id)}\s*&\s*\n\s*)(.*?)(\s*&)",
        re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        raise ValueError(f"Could not find question row for {id}")

    original = match.group(2).strip()
    if "RESOLVED" in original:
        return f"{id} is already marked resolved."

    new_text = (
        f"\\textit{{[RESOLVED --- {_today()}]}} {original} "
        f"Resolved: {resolution}"
    )
    _write("decisions_log.tex", content.replace(
        match.group(0),
        match.group(1) + new_text + match.group(3),
        1,
    ))
    return f"Resolved question {id}."


# ── ROADMAP tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def update_roadmap_item_status(search_text: str, new_status: str) -> str:
    """
    Flip the status tag on a specific \\item line in technical_roadmap.tex.
    search_text: unique fragment of the item text
                 e.g. 'Bring ioctl calls over TCP'
    new_status:  one of 'done', 'inprog', 'planned'
    """
    _validate_status(new_status)
    content = _read("technical_roadmap.tex")
    lines   = content.splitlines()
    idx     = next((i for i, ln in enumerate(lines) if search_text in ln), None)
    if idx is None:
        raise ValueError(f"Could not find line containing: {search_text!r}")
    lines[idx] = re.sub(r"\\(done|inprog|planned)", rf"\\{new_status}", lines[idx])
    _write("technical_roadmap.tex", "\n".join(lines))
    return f"Set \\{new_status} on item containing: {search_text!r}"


@mcp.tool()
def update_roadmap_phase_status(phase_title: str, new_status: str) -> str:
    """
    Flip the status tag on a phase section heading in technical_roadmap.tex.
    phase_title: text inside \\section{} e.g. 'Phase 1: GPIO End-to-End'
    new_status:  one of 'done', 'inprog', 'planned'
    """
    _validate_status(new_status)
    content = _read("technical_roadmap.tex")
    pattern = re.compile(
        r"(\\section\{" + re.escape(phase_title) + r"\s*)\\(done|inprog|planned)(\})"
    )
    if not pattern.search(content):
        raise ValueError(f"Could not find section heading: {phase_title!r}")
    _write("technical_roadmap.tex", pattern.sub(rf"\g<1>\\{new_status}\g<3>", content))
    return f"Set \\{new_status} on phase: {phase_title!r}"


@mcp.tool()
def append_roadmap_item(
    phase_title: str,
    subsection_title: str,
    item_text: str,
    status: str = "planned",
) -> str:
    """
    Add a new bullet to a subsection inside a phase in technical_roadmap.tex.
    phase_title:      e.g. 'Phase 1: GPIO End-to-End'
    subsection_title: e.g. 'In Progress'  or  'Completed'
    item_text:        item description — plain text, no \\item prefix needed
    status:           one of 'done', 'inprog', 'planned'

    The item is inserted before the closing \\end{itemize} of the target subsection.
    """
    _validate_status(status)
    content = _read("technical_roadmap.tex")

    pattern = re.compile(
        rf"(\\section\{{{re.escape(phase_title)}.*?\}}.*?"
        rf"\\subsection\{{{re.escape(subsection_title)}\}}.*?"
        rf"\\begin\{{itemize\}}[^%]*?)"
        rf"(\\end\{{itemize\}})",
        re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        raise ValueError(
            f"Could not find subsection '{subsection_title}' "
            f"inside phase '{phase_title}'"
        )

    new_item    = f"  \\item \\{status}\\ {item_text}\n"
    new_content = content[: match.start(2)] + new_item + content[match.start(2):]
    _write("technical_roadmap.tex", new_content)
    return f"Appended item to '{subsection_title}' in '{phase_title}'."


# ── BRANCH tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_current_branch() -> str:
    """
    Return the name of the currently checked-out git branch in DOCS_DIR.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(DOCS_DIR), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git error: {result.stderr.strip()}")
    return result.stdout.strip()


@mcp.tool()
def list_branches() -> str:
    """
    List all local git branches in DOCS_DIR.
    The current branch is prefixed with '* '.
    """
    result = subprocess.run(
        ["git", "branch"],
        cwd=str(DOCS_DIR), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git error: {result.stderr.strip()}")
    return result.stdout.strip()


@mcp.tool()
def switch_branch(branch_name: str) -> str:
    """
    Switch to an existing local branch in DOCS_DIR.
    Will fail if there are uncommitted changes — commit or stash them first.
    branch_name: e.g. 'main', 'dev', 'phase-2'
    """
    result = subprocess.run(
        ["git", "checkout", branch_name],
        cwd=str(DOCS_DIR), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git error: {result.stderr.strip()}")
    return f"Switched to branch '{branch_name}'."


@mcp.tool()
def create_branch(branch_name: str, switch_to: bool = True) -> str:
    """
    Create a new git branch in DOCS_DIR, branching from the current HEAD.
    branch_name: e.g. 'phase-2-docs'
    switch_to:   if True (default), checks out the new branch immediately
    """
    cmd = ["git", "checkout", "-b", branch_name] if switch_to else ["git", "branch", branch_name]
    result = subprocess.run(
        cmd, cwd=str(DOCS_DIR), capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git error: {result.stderr.strip()}")
    action = "Created and switched to" if switch_to else "Created"
    return f"{action} branch '{branch_name}'."


# ── BUILD + VCS tools ─────────────────────────────────────────────────────────

@mcp.tool()
def compile_doc(filename: str) -> str:
    """
    Run two xelatex passes on a .tex file.
    Returns 'ok' or the last 40 lines of the error log.
    Call this after editing to catch LaTeX errors early.
    """
    return _compile(filename)


@mcp.tool()
def compile_all() -> str:
    """
    Compile every .tex file in DOCS_DIR.
    Returns one status line per file.
    """
    results = []
    for tex in sorted(DOCS_DIR.glob("*.tex")):
        status = _compile(tex.name)
        results.append(f"{tex.name}: {status[:80]}")
    return "\n".join(results)


@mcp.tool()
def git_commit_push(message: str) -> str:
    """
    Stage all changes in DOCS_DIR, commit, and push to GitHub.
    Call once after a complete set of edits — not after every individual change.
    Good message format: 'docs: add D014, resolve Q005, mark Phase 1 item done'
    """
    cmds = [
        ["git", "pull", "--rebase"],
        ["git", "add", "."],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]
    output = []
    for cmd in cmds:
        result = subprocess.run(
            cmd, cwd=str(DOCS_DIR), capture_output=True, text=True
        )
        output.append(f"$ {' '.join(cmd)}")
        if result.stdout.strip():
            output.append(result.stdout.strip())
        if result.returncode != 0:
            output.append(f"ERROR: {result.stderr.strip()}")
            return "\n".join(output)
    return "\n".join(output)


# ── Optional API key auth ─────────────────────────────────────────────────────

if API_KEY:
    try:
        from fastmcp.middleware import Middleware
        from starlette.responses import JSONResponse

        class KeyAuth(Middleware):
            async def __call__(self, request, call_next):
                if request.headers.get("x-api-key", "") != API_KEY:
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
                return await call_next(request)

        mcp.add_middleware(KeyAuth)
    except ImportError:
        pass  # middleware API varies by fastmcp version — skip silently


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(
            transport="sse",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8000)),
        )
    else:
        mcp.run(transport="stdio")
