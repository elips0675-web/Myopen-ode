"""RAG - semantic code search via Ollama embeddings with disk caching."""

import json, os, glob, logging, hashlib
from pathlib import Path
import requests

log = logging.getLogger('rag')

OLLAMA_URL = "http://localhost:11434"
WORK_DIR = Path(".")
EMBED_MODEL = "nomic-embed-text"
RAG_INDEX = None
RAG_CHUNKS = []
RAG_DIRTY = True
RAG_CACHE_DIR = None

def init_rag(**kw):
    global OLLAMA_URL, WORK_DIR, EMBED_MODEL, RAG_CACHE_DIR
    for k, v in kw.items():
        if v is not None:
            globals()[k] = v
    if RAG_CACHE_DIR is None:
        RAG_CACHE_DIR = WORK_DIR / ".rag_cache"
        RAG_CACHE_DIR.mkdir(exist_ok=True)

def _cache_key():
    """Generate a cache key based on project files."""
    files = sorted(glob.glob(str(WORK_DIR / "**/*.py"), recursive=True))[:50]
    files += sorted(glob.glob(str(WORK_DIR / "**/*.js"), recursive=True))[:30]
    h = hashlib.md5()
    for fp in files[:20]:
        try: h.update((fp + str(Path(fp).stat().st_mtime)).encode())
        except: pass
    return h.hexdigest()[:16]

def _save_cache(key, chunks, index):
    if not RAG_CACHE_DIR: return
    cf = RAG_CACHE_DIR / f"{key}.json"
    try:
        data = {"chunks": chunks, "index": index, "model": EMBED_MODEL}
        cf.write_text(json.dumps(data), "utf-8")
        log.info("RAG cache saved: %s (%d chunks)", key, len(chunks))
    except Exception as e:
        log.warning("RAG cache save failed: %s", e)

def _load_cache(key):
    if not RAG_CACHE_DIR: return None
    cf = RAG_CACHE_DIR / f"{key}.json"
    if not cf.exists(): return None
    try:
        data = json.loads(cf.read_text())
        if data.get("model") != EMBED_MODEL: return None
        log.info("RAG cache loaded: %s (%d chunks)", key, len(data.get("chunks", [])))
        return data
    except Exception as e:
        log.warning("RAG cache load failed: %s", e)
        return None

def rag_index():
    global RAG_INDEX, RAG_CHUNKS, RAG_DIRTY
    if not RAG_DIRTY and RAG_INDEX: return

    # Try loading from cache first
    ck = _cache_key()
    cached = _load_cache(ck) if ck else None
    if cached:
        RAG_CHUNKS = cached["chunks"]
        RAG_INDEX = cached["index"]
        RAG_DIRTY = False
        return

    RAG_CHUNKS = []
    files = list(glob.glob(str(WORK_DIR / "**/*.py"), recursive=True))[:200]
    files += list(glob.glob(str(WORK_DIR / "**/*.js"), recursive=True))[:100]
    files += list(glob.glob(str(WORK_DIR / "**/*.ts"), recursive=True))[:100]
    files += list(glob.glob(str(WORK_DIR / "**/*.go"), recursive=True))[:50]
    files += list(glob.glob(str(WORK_DIR / "**/*.rs"), recursive=True))[:50]
    files += list(glob.glob(str(WORK_DIR / "**/*.java"), recursive=True))[:50]
    files += list(glob.glob(str(WORK_DIR / "**/*.json"), recursive=True))[:50]
    files += list(glob.glob(str(WORK_DIR / "**/*.md"), recursive=True))[:50]
    files += list(glob.glob(str(WORK_DIR / "**/.env*"), recursive=True))[:10]
    files += list(glob.glob(str(WORK_DIR / "**/*.env"), recursive=True))[:10]
    files += list(glob.glob(str(WORK_DIR / "**/*.yml"), recursive=True))[:30]
    files += list(glob.glob(str(WORK_DIR / "**/*.yaml"), recursive=True))[:30]
    files += list(glob.glob(str(WORK_DIR / "**/*.toml"), recursive=True))[:20]
    files += list(glob.glob(str(WORK_DIR / "**/*.cfg"), recursive=True))[:20]
    files += list(glob.glob(str(WORK_DIR / "**/*.ini"), recursive=True))[:20]
    for fp in files:
        p = Path(fp)
        if any(x in p.parts for x in (".git", "__pycache__", ".agent_backups", ".agent_sessions", "node_modules", ".venv", "venv")): continue
        if p.name.endswith(".exe") or p.name.endswith(".dll") or p.name.endswith(".bin"): continue
        try:
            text = p.read_text("utf-8", errors="ignore")
            rel = str(p.relative_to(WORK_DIR))
            chunks = []
            parts = text.split("\n")
            current = []; current_start = 0
            for i, line in enumerate(parts):
                if line.startswith(("def ", "class ", "async def ")) and len(current) > 5:
                    chunks.append(("\n".join(current), rel, current_start))
                    current = [line]; current_start = i
                else:
                    current.append(line)
            if current:
                chunks.append(("\n".join(current), rel, current_start))
            for chunk_text, chunk_file, chunk_line in chunks:
                RAG_CHUNKS.append({"text": chunk_text[:500], "file": chunk_file, "line": chunk_line})
        except Exception as e:
            log.warning("RAG file read: %s", e)

    if not RAG_CHUNKS: return
    try:
        texts = [c["text"] for c in RAG_CHUNKS]
        r = requests.post(f"{OLLAMA_URL}/api/embed", json={
            "model": EMBED_MODEL, "input": texts
        }, timeout=120)
        data = r.json()
        if "embeddings" in data:
            RAG_INDEX = data["embeddings"]
            RAG_DIRTY = False
            _save_cache(ck, RAG_CHUNKS, RAG_INDEX)
    except Exception as e:
        log.warning("RAG embed failed: %s", e)

def _cos_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = sum(x*x for x in a)**0.5
    nb = sum(y*y for y in b)**0.5
    return dot / (na * nb + 1e-10)

def rag_search(query, top_k=5):
    rag_index()
    if RAG_INDEX is None or not RAG_CHUNKS: return "RAG not available"
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embed", json={
            "model": EMBED_MODEL, "input": [query]
        }, timeout=30)
        q_emb = r.json().get("embeddings", [[]])[0]
        if not q_emb: return "No embedding for query"
        scores = [(_cos_sim(q_emb, emb), i) for i, emb in enumerate(RAG_INDEX)]
        scores.sort(key=lambda x: -x[0])
        results = []
        for score, idx in scores[:top_k]:
            c = RAG_CHUNKS[idx]
            results.append(f"[{score:.2f}] {c['file']}:{c['line']}\n{c['text'][:300]}")
        return "\n---\n".join(results)
    except Exception as e:
        return f"RAG search error: {e}"
