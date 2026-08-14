"""Overleaf MCP — edit and compile Overleaf projects via session-cookie auth.

Works on free Overleaf accounts (no premium Git integration needed).
Auth: the `overleaf_session2` browser cookie, via OVERLEAF_SESSION_COOKIE
(env or .env next to this file).
"""

import os
import fnmatch
from pathlib import Path

import pyoverleaf
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv(Path(__file__).parent / ".env")

COOKIE_HELP = (
    "Overleaf session expired or invalid. Fix: log in at www.overleaf.com, open "
    "DevTools > Application > Cookies > https://www.overleaf.com, copy the value of "
    "'overleaf_session2', and update OVERLEAF_SESSION_COOKIE in "
    f"{Path(__file__).parent / '.env'} (then restart the MCP server)."
)

mcp = FastMCP("overleaf")

_api = None
_last_compile: dict[str, dict] = {}  # project_id -> last compile response JSON


def api() -> pyoverleaf.Api:
    global _api
    if _api is None:
        cookie = os.environ.get("OVERLEAF_SESSION_COOKIE")
        if not cookie:
            raise RuntimeError("OVERLEAF_SESSION_COOKIE is not set. " + COOKIE_HELP)
        a = pyoverleaf.Api()
        a.login_from_cookies({"overleaf_session2": cookie})
        _api = a
    return _api


def _projects():
    try:
        return api().get_projects()
    except RuntimeError as e:
        raise RuntimeError(COOKIE_HELP) from e


def resolve_project(project: str):
    """Resolve a project by exact id, exact name, or unique name substring."""
    projects = _projects()
    by_id = [p for p in projects if p.id == project]
    if by_id:
        return by_id[0]
    exact = [p for p in projects if p.name.lower() == project.lower()]
    if len(exact) == 1:
        return exact[0]
    sub = [p for p in projects if project.lower() in p.name.lower()]
    if len(sub) == 1:
        return sub[0]
    if len(sub) > 1:
        names = ", ".join(f"'{p.name}'" for p in sub)
        raise ValueError(f"Ambiguous project '{project}' — matches: {names}. Be more specific.")
    raise ValueError(
        f"No project matching '{project}'. Use list_projects to see available projects."
    )


def _walk(folder, prefix=""):
    out = []
    for child in folder.children:
        kind = getattr(child, "type", "folder")
        path = prefix + child.name
        if kind == "folder":
            out.extend(_walk(child, path + "/"))
        else:
            out.append((path, kind, child))
    return out


def _find_entity(project_id: str, path: str):
    root = api().project_get_files(project_id)
    for p, _kind, entity in _walk(root):
        if p == path:
            return entity
    return None


def _folder_for(project_id: str, path: str):
    """Return (folder_id, file_name), creating intermediate folders as needed."""
    root = api().project_get_files(project_id)
    parts = path.split("/")
    folder = root
    for name in parts[:-1]:
        nxt = next(
            (c for c in folder.children if getattr(c, "type", "folder") == "folder" and c.name == name),
            None,
        )
        if nxt is None:
            nxt = api().project_create_folder(project_id, folder.id, name)
        folder = nxt
    return folder.id, parts[-1]


def _compile(project_id: str) -> dict:
    a = api()
    sess = a._get_session()  # noqa: SLF001 — pyoverleaf keeps these private but stable
    csrf = a._get_csrf_token(project_id)  # noqa: SLF001
    r = sess.post(
        f"https://www.overleaf.com/project/{project_id}/compile?auto_compile=true",
        json={"rootDoc_id": None, "draft": False, "check": "silent",
              "incrementalCompileEnabled": True},
        headers={"x-csrf-token": csrf, "Accept": "application/json"},
        timeout=120,
    )
    if r.status_code in (401, 403) or "login" in str(r.url):
        raise RuntimeError(COOKIE_HELP)
    r.raise_for_status()
    data = r.json()
    _last_compile[project_id] = data
    return data


def _fetch_output(project_id: str, filename: str) -> bytes:
    data = _last_compile.get(project_id) or _compile(project_id)
    entry = next((f for f in data.get("outputFiles", []) if f["path"] == filename), None)
    if entry is None:
        raise ValueError(f"No {filename} in last compile output (status: {data.get('status')}).")
    url = entry["url"]
    if url.startswith("/"):
        url = "https://www.overleaf.com" + url
    params = {}
    if data.get("clsiServerId"):
        params["clsiserverid"] = data["clsiServerId"]
    sess = api()._get_session()  # noqa: SLF001
    r = sess.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.content


@mcp.tool()
def list_projects() -> str:
    """List all Overleaf projects on the account (id | name)."""
    lines = [f"{p.id} | {p.name}" for p in _projects()]
    return "\n".join(lines) or "No projects found."


@mcp.tool()
def list_files(project: str, pattern: str = "*") -> str:
    """List files in a project. `project` is an id, name, or unique name substring.
    Optional glob `pattern` filters by path (e.g. '*.tex')."""
    p = resolve_project(project)
    entries = _walk(api().project_get_files(p.id))
    lines = [f"{path} ({kind})" for path, kind, _ in entries if fnmatch.fnmatch(path, pattern)]
    return f"Project: {p.name} ({p.id})\n" + ("\n".join(lines) or "No matching files.")


@mcp.tool()
def read_file(project: str, path: str) -> str:
    """Read a file from a project. `path` is relative, e.g. 'main.tex' or 'sections/edu.tex'."""
    p = resolve_project(project)
    entity = _find_entity(p.id, path)
    if entity is None:
        raise ValueError(f"No file '{path}' in project '{p.name}'. Use list_files.")
    return api().project_download_file(p.id, entity).decode("utf-8", errors="replace")


@mcp.tool()
def write_file(project: str, path: str, content: str) -> str:
    """Create or overwrite a file in a project. Overwriting keeps the same doc id,
    so Overleaf's history is preserved. Missing folders in `path` are created."""
    p = resolve_project(project)
    folder_id, name = _folder_for(p.id, path)
    api().project_upload_file(p.id, folder_id, name, content.encode("utf-8"))
    return f"Wrote {path} ({len(content)} chars) to project '{p.name}'."


@mcp.tool()
def compile_project(project: str) -> str:
    """Compile a project on Overleaf's servers. Returns status; on failure, includes
    the tail of the LaTeX log so errors can be fixed."""
    p = resolve_project(project)
    data = _compile(p.id)
    status = data.get("status", "unknown")
    outputs = [f["path"] for f in data.get("outputFiles", [])]
    msg = f"Compile status for '{p.name}': {status}."
    if "output.pdf" in outputs:
        msg += " PDF is ready — view it at https://www.overleaf.com/project/" + p.id
    if status != "success":
        try:
            log = _fetch_output(p.id, "output.log").decode("utf-8", errors="replace")
            msg += "\n\n--- log tail ---\n" + log[-3000:]
        except Exception:
            msg += " (Could not fetch compile log.)"
    return msg


@mcp.tool()
def get_compile_log(project: str) -> str:
    """Full LaTeX log (output.log) from the most recent compile (compiles first if needed)."""
    p = resolve_project(project)
    log = _fetch_output(p.id, "output.log").decode("utf-8", errors="replace")
    return log[-20000:]


@mcp.tool()
def download_pdf(project: str, dest_path: str) -> str:
    """Download the compiled output.pdf from the most recent compile to a local path
    (compiles first if needed)."""
    p = resolve_project(project)
    pdf = _fetch_output(p.id, "output.pdf")
    dest = Path(dest_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(pdf)
    return f"Saved {len(pdf)} bytes to {dest}."


if __name__ == "__main__":
    mcp.run()
