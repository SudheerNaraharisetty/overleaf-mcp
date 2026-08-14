# Overleaf MCP

An MCP (Model Context Protocol) server that lets AI assistants like Claude read, edit, and compile your [Overleaf](https://www.overleaf.com) projects.

Works with **free Overleaf accounts** — no premium Git integration required. It authenticates with your browser session cookie and talks to Overleaf's web API via [pyoverleaf](https://github.com/jkulhanek/pyoverleaf).

## Tools

| Tool | Description |
|------|-------------|
| `list_projects` | List all projects on your Overleaf account |
| `list_files` | List files in a project (supports glob filters like `*.tex`) |
| `read_file` | Read any file from a project |
| `write_file` | Create or overwrite a file (preserves Overleaf history; creates folders as needed) |
| `compile_project` | Compile on Overleaf's servers; returns the log tail on failure |
| `get_compile_log` | Fetch the full LaTeX log from the latest compile |
| `download_pdf` | Download the compiled PDF to a local path |

Projects can be referenced by id, exact name, or a unique name substring — e.g. `read_file("thesis", "main.tex")`.

## Setup

### 1. Clone and install

```bash
git clone https://github.com/SudheerNaraharisetty/overleaf-mcp.git
cd overleaf-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Get your Overleaf session cookie

1. Log in at [www.overleaf.com](https://www.overleaf.com)
2. Open browser DevTools (F12) → **Application** (Chrome) or **Storage** (Firefox) → **Cookies** → `https://www.overleaf.com`
3. Copy the value of the **`overleaf_session2`** cookie

### 3. Configure the cookie

Create a `.env` file next to `server.py`:

```bash
echo 'OVERLEAF_SESSION_COOKIE=<paste cookie value here>' > .env
```

> **Note:** The cookie expires when your Overleaf session does. If the server starts returning auth errors, grab a fresh cookie and update `.env`.

### 4. Add to your MCP client

**Claude Code:**

```bash
claude mcp add overleaf -- /path/to/overleaf-mcp/.venv/bin/python /path/to/overleaf-mcp/server.py
```

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "overleaf": {
      "command": "/path/to/overleaf-mcp/.venv/bin/python",
      "args": ["/path/to/overleaf-mcp/server.py"]
    }
  }
}
```

(Any other MCP client works the same way — run `server.py` with the venv's Python over stdio.)

### 5. Try it

Ask your assistant something like:

> "List my Overleaf projects"
> "Fix the compile errors in my thesis project"
> "Update the abstract in main.tex and recompile"

## How it works

- Authenticates with the `overleaf_session2` cookie (same session your browser uses)
- Reads/writes files through Overleaf's project API — edits show up live in the web editor and in project history
- Compiles run on Overleaf's servers, so you get the exact same output as clicking "Recompile"

## Security notes

- Your session cookie grants full access to your Overleaf account — keep `.env` private (it's gitignored)
- The server runs locally over stdio; nothing is exposed to the network

## License

MIT
