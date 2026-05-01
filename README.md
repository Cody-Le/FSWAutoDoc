# Space FSW Docs — MCP Server

MCP server that gives Claude live read/write access to the LaTeX docs.
No more manual re-uploads. No more "update the docs" at the end of every session.

## Tools exposed to Claude

**Read**

| Tool | What it does |
|---|---|
| `list_docs()` | List all `.tex` files in DOCS_DIR |
| `get_doc(filename)` | Return full source of any `.tex` file |

**Generic edit — works on any `.tex` file**

| Tool | What it does |
|---|---|
| `str_replace_in_doc(filename, old, new)` | Surgical edit on any doc — `architecture_overview.tex`, `system_diagram.tex`, etc. `old` must match exactly once. |
| `create_doc(filename, title, subtitle, body)` | Create a new doc from the shared preamble. Preamble (colors, fonts, header) injected automatically — supply body content only. Refuses to overwrite existing files. |

**Decisions log**

| Tool | What it does |
|---|---|
| `add_architecture_decision(id, decision, rationale, alternatives)` | Append row to Architecture Decisions table |
| `add_strategic_decision(id, decision, rationale, notes)` | Append row to Strategic Decisions table |
| `add_open_question(id, question, context)` | Append row to Open Questions table |
| `resolve_open_question(id, resolution)` | Mark question resolved inline with date |

**Roadmap**

| Tool | What it does |
|---|---|
| `update_roadmap_item_status(search_text, new_status)` | Flip `\planned`/`\inprog`/`\done` on a specific bullet item |
| `update_roadmap_phase_status(phase_title, new_status)` | Flip status tag on a phase section heading |
| `append_roadmap_item(phase_title, subsection_title, item_text, status)` | Add a new bullet to any phase subsection |

**Branch management**

| Tool | What it does |
|---|---|
| `get_current_branch()` | Return the currently checked-out branch name |
| `list_branches()` | List all local branches (`*` marks current) |
| `switch_branch(branch_name)` | Checkout an existing branch — fails if uncommitted changes exist |
| `create_branch(branch_name, switch_to)` | Create a new branch from HEAD; switches to it by default |

**Build + VCS**

| Tool | What it does |
|---|---|
| `compile_doc(filename)` | Two-pass xelatex, returns `ok` or last 40 lines of error log |
| `compile_all()` | Compile every `.tex` in DOCS_DIR |
| `git_commit_push(message)` | Pull (rebase), stage all, commit, push to GitHub |

---

## Local dev

```bash
pip install fastmcp
DOCS_DIR=./docs python server.py          # stdio transport
```

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "space-fsw-docs": {
      "command": "python3",
      "args": ["/path/to/server.py"],
      "env": { "DOCS_DIR": "/path/to/docs" }
    }
  }
}
```

---

## Deploy to Fly.io (free, always-on)

### 1. Install flyctl
```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

### 2. First deploy
```bash
fly launch          # detects Dockerfile, creates app
fly volumes create docs_volume --size 1   # persistent disk for docs
fly deploy
```

### 3. Set secrets
```bash
fly secrets set API_KEY=your-secret-key-here
fly secrets set GIT_TOKEN=your-github-pat-here   # needs repo write access
```

### 4. Clone your docs repo into the volume
```bash
fly ssh console
cd /data
git clone https://$GIT_TOKEN@github.com/YOURUSERNAME/space-fsw-docs docs
exit
```

### 5. Connect Claude to the server
In Claude.ai → Settings → Integrations → Add MCP Server:
```
URL:         https://space-fsw-docs.fly.dev/sse
Header name: x-api-key
Header value: your-secret-key-here
```

### Updates
```bash
fly deploy     # redeploy after changing server.py
```

---

## GitHub PAT setup

The server needs a token to push commits. In GitHub:
Settings → Developer settings → Personal access tokens → Fine-grained tokens
- Repository access: your docs repo only
- Permissions: Contents → Read and write

Set the remote to use the token so `git push` works without a prompt:
```bash
# inside fly ssh console, inside /data/docs:
git remote set-url origin https://<token>@github.com/<you>/space-fsw-docs
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DOCS_DIR` | `./docs` | Path to the directory containing `.tex` files |
| `API_KEY` | *(empty)* | If set, all requests must include `x-api-key` header |
| `MCP_TRANSPORT` | `stdio` | `stdio` for local, `sse` for deployed |
| `PORT` | `8000` | HTTP port for SSE transport |
