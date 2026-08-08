"""File browser / editor / upload API routes (extracted from agent.py)."""
import os
from pathlib import Path
from fastapi import APIRouter
import agent as _agent
from agent import build_tree, FileUploadReq
from tools import backup

router = APIRouter()

@router.get("/api/files")
def get_files(path: str = "."):
    return {"tree": build_tree(path), "current": path}

@router.get("/api/file")
def get_file(path: str):
    p = _agent.WORK_DIR / path if not os.path.isabs(path) else Path(path)
    if not p.exists() or p.is_dir(): return {"error": "Not found"}
    return {"content": p.read_text("utf-8", errors="ignore"), "path": path}

@router.put("/api/file")
def save_file(req: FileUploadReq):
    p = _agent.WORK_DIR / req.path if not os.path.isabs(req.path) else Path(req.path)
    if p.is_dir(): return {"error": "Is a directory"}
    p.parent.mkdir(parents=True, exist_ok=True)
    backup(req.path)
    p.write_text(req.content, "utf-8")
    return {"ok": True, "path": req.path, "size": len(req.content)}

@router.post("/api/upload")
async def upload_file(req: FileUploadReq):
    p = _agent.WORK_DIR / req.path if not os.path.isabs(req.path) else Path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content, "utf-8")
    return {"ok": True, "path": req.path, "size": len(req.content)}
