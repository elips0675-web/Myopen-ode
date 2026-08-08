"""Session CRUD + search/export/import API routes (extracted from agent.py)."""
import json
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import agent as _agent
from agent import (_db, load_session, save_session, delete_session_db,
                   list_sessions_db, session_interrupted, ChatReq, SessionReq)

router = APIRouter()

@router.get("/api/sessions")
def list_sessions():
    sessions = list_sessions_db()
    for s in sessions:
        s["interrupted"] = session_interrupted(s["id"])
    return sessions

@router.get("/api/sessions/search")
def search_sessions(q: str = "", limit: int = 20):
    """Full-text search across session messages (SQLite LIKE + JSON fallback)."""
    if not q.strip():
        return []
    ql = q.lower().strip()
    results = []
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT id, title, messages, updated FROM sessions WHERE lower(messages) LIKE ? ORDER BY updated DESC LIMIT ?",
                (f"%{ql}%", limit)).fetchall()
        for sid, title, raw, updated in rows:
            snippets = []
            try:
                msgs = json.loads(raw)
                for m in msgs:
                    c = m.get("content", "")
                    if isinstance(c, str) and ql in c.lower():
                        i = c.lower().find(ql)
                        a = max(0, i - 80)
                        snippets.append("…" + c[a:i + len(q) + 80].replace("\n", " ") + "…")
            except Exception:
                pass
            results.append({"id": sid, "title": title, "updated": updated,
                            "snippets": snippets[:3], "matches": len(snippets)})
    except Exception as e:
        _agent.log.warning("Session search db: %s", e)
    for f in sorted(_agent.SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if any(r["id"] == f.stem for r in results):
            continue
        try:
            data = json.loads(f.read_text())
            msgs = data.get("messages", [])
            snippets = []
            for m in msgs:
                c = m.get("content", "")
                if isinstance(c, str) and ql in c.lower():
                    i = c.lower().find(ql)
                    a = max(0, i - 80)
                    snippets.append("…" + c[a:i + len(q) + 80].replace("\n", " ") + "…")
            if snippets:
                results.append({"id": f.stem, "title": data.get("title", f.stem),
                                "updated": data.get("updated", ""),
                                "snippets": snippets[:3], "matches": len(snippets)})
        except Exception:
            continue
    return results[:limit]

@router.post("/api/sessions")
def create_session(req: SessionReq):
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = req.title or f"Session {sid}"
    save_session(sid, title, [], datetime.now().isoformat())
    return {"id": sid, "title": title}

@router.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = load_session(sid)
    if s is None: return {"error": "Not found"}
    s["interrupted"] = session_interrupted(sid)
    return s

@router.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    delete_session_db(sid)
    return {"ok": True}

@router.get("/api/sessions/{sid}/export")
def export_session(sid: str):
    s = load_session(sid)
    if s is None: return {"error": "Not found"}
    return JSONResponse(content=s)

@router.post("/api/sessions/import")
def import_session(req: ChatReq):
    data = json.loads(req.model_dump_json())
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = data.get("title", f"Imported {sid}")
    messages = data.get("messages", data.get("content", []))
    if isinstance(messages, str):
        try: messages = json.loads(messages)
        except: messages = []
    save_session(sid, title, messages, datetime.now().isoformat())
    return {"id": sid, "title": title}
