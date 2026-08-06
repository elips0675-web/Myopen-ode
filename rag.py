"""RAG - semantic code search via Ollama embeddings with incremental disk cache + hybrid BM25."""

import json, os, glob, logging, hashlib, math, re, threading, time
from pathlib import Path
import requests

try:
    import numpy as _np
except ImportError:
    _np = None
try:
    import faiss as _faiss
except ImportError:
    _faiss = None

log = logging.getLogger('rag')

OLLAMA_URL = "http://localhost:11434"
WORK_DIR = Path(".")
EMBED_MODEL = "nomic-embed-text"
RAG_INDEX = None
RAG_CHUNKS = []
RAG_DIRTY = True
RAG_CACHE_DIR = None
FAISS_INDEX = None
RAG_MAX_CHUNKS = int(os.environ.get("RAG_MAX_CHUNKS", "6000"))
_FILE_STATS = {}   # rel path -> (mtime, size) from last index
BM25_DF = {}       # term -> doc frequency
BM25_N = 0         # doc count
BM25_AVGLEN = 1.0
RAG_LOCK = threading.RLock()  # thread safety (uvicorn multi-threaded)

RAG_STATUS = {"phase": "idle", "files_done": 0, "files_total": 0,
              "chunks": 0, "updated": 0.0}  # indexing progress for the UI

EXT_PATTERNS = [
    ("**/*.py", 200), ("**/*.js", 100), ("**/*.ts", 100), ("**/*.go", 50),
    ("**/*.rs", 50), ("**/*.java", 50), ("**/*.json", 50), ("**/*.md", 50),
    ("**/.env*", 10), ("**/*.yml", 30), ("**/*.yaml", 30), ("**/*.toml", 20),
    ("**/*.cfg", 20), ("**/*.ini", 20),
]
SKIP_PARTS = (".git", "__pycache__", ".agent_backups", ".agent_sessions",
              ".rag_cache", "node_modules", ".venv", "venv")

def init_rag(**kw):
    global OLLAMA_URL, WORK_DIR, EMBED_MODEL, RAG_CACHE_DIR
    for k, v in kw.items():
        if v is not None:
            globals()[k] = v
    if RAG_CACHE_DIR is None:
        RAG_CACHE_DIR = WORK_DIR / ".rag_cache"
        RAG_CACHE_DIR.mkdir(exist_ok=True)

def _scan_files():
    files = []
    for pattern, limit in EXT_PATTERNS:
        files += list(glob.glob(str(WORK_DIR / pattern), recursive=True))[:limit]
    out = []
    for fp in files:
        p = Path(fp)
        if any(x in p.parts for x in SKIP_PARTS): continue
        if p.name.endswith((".exe", ".dll", ".bin", ".png", ".jpg", ".ico")): continue
        try:
            st = p.stat()
            out.append((str(p.relative_to(WORK_DIR)), st.st_mtime, st.st_size))
        except: pass
    return out

def _file_cache_path(rel):
    h = hashlib.md5(rel.encode()).hexdigest()[:16]
    return RAG_CACHE_DIR / f"file_{h}.json"

def _load_file_cache(rel, mtime, size):
    cf = _file_cache_path(rel)
    if not cf.exists(): return None
    try:
        data = json.loads(cf.read_text())
        if data.get("mtime") == mtime and data.get("size") == size and data.get("model") == EMBED_MODEL:
            chunks = data.get("chunks", [])
            embs = data.get("embeddings", [])
            for c, e in zip(chunks, embs):
                c["emb"] = e
                c["_toks"] = _tokenize(c["text"])
            return chunks
    except: pass
    return None

def _save_file_cache(rel, mtime, size, chunks, embeddings):
    cf = _file_cache_path(rel)
    try:
        cf.write_text(json.dumps({
            "mtime": mtime, "size": size, "model": EMBED_MODEL,
            "chunks": chunks, "embeddings": embeddings
        }), "utf-8")
    except Exception as e:
        log.warning("File cache save %s: %s", rel, e)

def _tokenize(text):
    return [t.lower() for t in re.findall(r"[a-zа-я0-9_]+", text)]

def _build_bm25():
    global BM25_DF, BM25_N, BM25_AVGLEN
    BM25_DF = {}
    BM25_N = len(RAG_CHUNKS)
    total_len = 0
    for c in RAG_CHUNKS:
        toks = c.get("_toks") or []
        seen = set(toks)
        for t in seen: BM25_DF[t] = BM25_DF.get(t, 0) + 1
        total_len += len(toks)
    BM25_AVGLEN = max(1.0, total_len / max(1, BM25_N))

def bm25_score(query, doc_idx):
    if not BM25_N: return 0.0
    toks = _tokenize(query)
    c = RAG_CHUNKS[doc_idx]
    doc_toks = c.get("_toks") or []
    doc_len = max(1, len(doc_toks))
    from collections import Counter
    tf = Counter(doc_toks)
    k1, b = 1.5, 0.75
    score = 0.0
    for t in toks:
        df = BM25_DF.get(t, 0)
        if df == 0: continue
        idf = math.log((BM25_N - df + 0.5) / (df + 0.5) + 1)
        f = tf.get(t, 0)
        score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / BM25_AVGLEN))
    return score

def rag_index():
    global RAG_INDEX, RAG_CHUNKS, RAG_DIRTY
    with RAG_LOCK:
        files = _scan_files()
        changed, removed = [], []
        for rel, mtime, size in files:
            old = _FILE_STATS.get(rel)
            if old != (mtime, size): changed.append((rel, mtime, size))
        removed = [rel for rel in _FILE_STATS if rel not in {f[0] for f in files}]

        RAG_STATUS.update({"phase": "indexing", "files_done": 0,
                           "files_total": len(files), "chunks": len(RAG_CHUNKS or [])})

        if not RAG_CHUNKS:
            # cold start: load everything from file caches
            RAG_CHUNKS = []
            for rel, mtime, size in files:
                chunks = _load_file_cache(rel, mtime, size)
                if chunks:
                    RAG_CHUNKS += chunks
                    _FILE_STATS[rel] = (mtime, size)
                RAG_STATUS["files_done"] += 1

        if removed or changed:
            # rebuild: drop old entries for changed/removed files, re-embed changed
            keep = [c for c in RAG_CHUNKS if c["file"] not in changed and c["file"] not in removed]
            RAG_CHUNKS = keep
            for rel in removed:
                _FILE_STATS.pop(rel, None)
            for rel, mtime, size in changed:
                _index_file(rel, mtime, size)
                RAG_STATUS["files_done"] += 1

        if not RAG_CHUNKS:
            RAG_STATUS.update({"phase": "idle", "updated": time.time()})
            return
        if not changed and not removed and RAG_INDEX and not RAG_DIRTY:
            RAG_STATUS.update({"phase": "idle", "chunks": len(RAG_CHUNKS), "updated": time.time()})
            return  # nothing changed since last index
        if RAG_MAX_CHUNKS and len(RAG_CHUNKS) > RAG_MAX_CHUNKS:
            # hard memory cap: drop oldest chunks (newest files were appended last)
            log.warning("RAG: memory cap %d, truncating %d chunks",
                        RAG_MAX_CHUNKS, len(RAG_CHUNKS) - RAG_MAX_CHUNKS)
            RAG_CHUNKS = RAG_CHUNKS[-RAG_MAX_CHUNKS:]
        _build_bm25()
        RAG_INDEX = [c["emb"] for c in RAG_CHUNKS]
        _rebuild_fast_index()
        RAG_DIRTY = False
        RAG_STATUS.update({"phase": "idle", "chunks": len(RAG_CHUNKS), "updated": time.time()})

def _rebuild_fast_index():
    """Build a FAISS (or numpy) index for fast vector search; falls back to
    pure-Python cosine in rag_search when neither is available."""
    global FAISS_INDEX
    FAISS_INDEX = None
    if not RAG_INDEX or _np is None:
        return
    dim = len(RAG_INDEX[0]) if isinstance(RAG_INDEX[0], (list, tuple)) else 0
    rows = [e for e in RAG_INDEX
            if isinstance(e, (list, tuple)) and len(e) == dim and dim > 0]
    if len(rows) != len(RAG_INDEX):
        log.warning("RAG: skipping %d malformed embeddings (expected dim %d)",
                    len(RAG_INDEX) - len(rows), dim)
    if not rows:
        return
    mat = _np.asarray(rows, dtype="float32")
    if _faiss is not None:
        try:
            idx = _faiss.IndexFlatIP(mat.shape[1])
            idx.add(mat)
            FAISS_INDEX = idx
            return
        except Exception as e:
            log.warning("FAISS build failed, numpy fallback: %s", e)
    FAISS_INDEX = "numpy"  # marker: vectorized matmul search below

def _split_chunk(text, size=500, overlap=80):
    """Split long chunks into ~size-char pieces with overlap so context at
    boundaries is not lost (works for any language, not just def/class)."""
    if len(text) <= size:
        return [text]
    parts = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + size, n)
        parts.append(text[i:end])
        if end == n:
            break
        i = max(i + size - overlap, i + 1)
    return parts

def _index_file(rel, mtime, size):
    global RAG_CHUNKS
    cached = _load_file_cache(rel, mtime, size)
    if cached:
        RAG_CHUNKS += cached
        _FILE_STATS[rel] = (mtime, size)
        return
    p = WORK_DIR / rel
    try:
        text = p.read_text("utf-8", errors="ignore")
    except Exception as e:
        log.warning("RAG read %s: %s", rel, e)
        return
    chunks = []
    parts = text.split("\n")
    current = []; current_start = 0
    for i, line in enumerate(parts):
        if line.startswith(("def ", "class ", "async def ", "func ", "type ", "struct ", "pub fn ")) and len(current) > 5:
            chunks.append(("\n".join(current), rel, current_start))
            current = [line]; current_start = i
        else:
            current.append(line)
    if current:
        chunks.append(("\n".join(current), rel, current_start))
    # size-based re-chunking with overlap (language-agnostic)
    chunk_data = []
    for t, r, ln in chunks:
        for piece in _split_chunk(t):
            chunk_data.append({"text": piece, "file": rel, "line": ln, "emb": []})
    if not chunk_data: return
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embed", json={
            "model": EMBED_MODEL, "input": [c["text"] for c in chunk_data]
        }, timeout=120)
        embs = r.json().get("embeddings", [])
        for c, e in zip(chunk_data, embs):
            c["emb"] = e
    except Exception as e:
        log.warning("RAG embed %s: %s", rel, e)
        for c in chunk_data: c["emb"] = [0.0]
    for c in chunk_data:
        c["_toks"] = _tokenize(c["text"])
    RAG_CHUNKS += chunk_data
    _FILE_STATS[rel] = (mtime, size)
    _save_file_cache(rel, mtime, size,
                     [{"text": c["text"], "file": c["file"], "line": c["line"]} for c in chunk_data],
                     [c["emb"] for c in chunk_data])
    log.info("RAG indexed: %s (%d chunks)", rel, len(chunk_data))

def _cos_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = sum(x*x for x in a)**0.5
    nb = sum(y*y for y in b)**0.5
    return dot / (na * nb + 1e-10)

def _schedule_bg_index():
    """Run re-indexing in a background thread so searches never block on it
    (after the cold start). Deduplicates concurrent scheduling."""
    global _BG_THREAD
    with RAG_LOCK:
        if _BG_THREAD and _BG_THREAD.is_alive():
            return
        _BG_THREAD = threading.Thread(target=_bg_index_work, daemon=True)
        _BG_THREAD.start()

def _bg_index_work():
    try:
        rag_index()
    except Exception as e:
        log.warning("Background RAG index failed: %s", e)

_BG_THREAD = None

def _chunk_scope(chunk):
    """Top-level folder of the chunk's file (RAG folder segmentation)."""
    rel = chunk.get("file", "").replace("\\", "/").strip("/")
    return rel.split("/")[0] if "/" in rel else ""


def rag_search(query, top_k=5, hybrid=True, scope=None):
    with RAG_LOCK:
        if RAG_INDEX is None:
            rag_index()  # cold start: synchronous so the first search has data
        else:
            _schedule_bg_index()  # subsequent re-indexes happen in background
        if RAG_INDEX is None or not RAG_CHUNKS: return "RAG not available"
        try:
            r = requests.post(f"{OLLAMA_URL}/api/embed", json={
                "model": EMBED_MODEL, "input": [query]
            }, timeout=30)
            q_emb = r.json().get("embeddings", [[]])[0]
            if not q_emb: return "No embedding for query"
            if scope:
                # folder-scoped search: only chunks under <scope>/ (cheap linear pass)
                scope = str(scope).strip().strip("/\\")
                keep = [i for i in range(len(RAG_CHUNKS)) if _chunk_scope(RAG_CHUNKS[i]).startswith(scope)]
                if not keep:
                    return f"No RAG chunks under folder '{scope}'"
                mat = _np.asarray([RAG_INDEX[i] for i in keep], dtype="float32") if _np else None
                if mat is None:
                    return "RAG scoped search needs numpy"
                q = _np.asarray(q_emb, dtype="float32")
                dots = mat @ q
                cos = dots / (_np.linalg.norm(mat, axis=1) * _np.linalg.norm(q) + 1e-10)
                sem = [(float(cos[j]), keep[j]) for j in range(len(keep))]
            elif FAISS_INDEX and _faiss is not None and FAISS_INDEX != "numpy":
                D, I = FAISS_INDEX.search(_np.asarray([q_emb], dtype="float32"),
                                          min(top_k, max(1, len(RAG_CHUNKS))))
                sem = [(float(D[0][j]), int(I[0][j])) for j in range(len(D[0]))]
            elif FAISS_INDEX == "numpy":
                mat = _np.asarray(RAG_INDEX, dtype="float32")
                q = _np.asarray(q_emb, dtype="float32")
                dots = mat @ q
                cos = dots / (_np.linalg.norm(mat, axis=1) * _np.linalg.norm(q) + 1e-10)
                sem = [(float(cos[i]), i) for i in range(len(RAG_CHUNKS))]
            else:
                sem = [(_cos_sim(q_emb, emb), i) for i, emb in enumerate(RAG_INDEX)]
            if hybrid:
                bm = [bm25_score(query, i) for i in range(len(RAG_CHUNKS))]
                bmax = max(bm) if bm and max(bm) > 0 else 1.0
                scores = [((sem[i][0] + 0.4 * (bm[i] / bmax)), i) for i in range(len(sem))]
            else:
                scores = sem
            scores.sort(key=lambda x: -x[0])
            results = []
            for score, idx in scores[:top_k]:
                c = RAG_CHUNKS[idx]
                results.append(f"[{score:.2f}] {c['file']}:{c['line']}\n{c['text'][:300]}")
            return "\n---\n".join(results)
        except Exception as e:
            return f"RAG search error: {e}"
