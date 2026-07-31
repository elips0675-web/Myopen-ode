"""RAG - semantic code search via Ollama embeddings with incremental disk cache + hybrid BM25."""

import json, os, glob, logging, hashlib, math, re
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
_FILE_STATS = {}   # rel path -> (mtime, size) from last index
BM25_DF = {}       # term -> doc frequency
BM25_N = 0         # doc count
BM25_AVGLEN = 1.0

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
    if not RAG_DIRTY and RAG_INDEX: return

    files = _scan_files()
    changed, removed = [], []
    for rel, mtime, size in files:
        old = _FILE_STATS.get(rel)
        if old != (mtime, size): changed.append((rel, mtime, size))
    removed = [rel for rel in _FILE_STATS if rel not in {f[0] for f in files}]

    if not RAG_CHUNKS:
        # cold start: load everything from file caches
        RAG_CHUNKS = []
        for rel, mtime, size in files:
            chunks = _load_file_cache(rel, mtime, size)
            if chunks:
                RAG_CHUNKS += chunks
                _FILE_STATS[rel] = (mtime, size)

    if removed or changed:
        # rebuild: drop old entries for changed/removed files, re-embed changed
        keep = [c for c in RAG_CHUNKS if c["file"] not in changed and c["file"] not in removed]
        RAG_CHUNKS = keep
        for rel in removed:
            _FILE_STATS.pop(rel, None)
        for rel, mtime, size in changed:
            _index_file(rel, mtime, size)

    if not RAG_CHUNKS: return
    _build_bm25()
    RAG_INDEX = [c["emb"] for c in RAG_CHUNKS]
    RAG_DIRTY = False

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
    chunk_data = [{"text": t[:500], "file": rel, "line": ln, "emb": []} for t, r, ln in chunks]
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

def rag_search(query, top_k=5, hybrid=True):
    rag_index()
    if RAG_INDEX is None or not RAG_CHUNKS: return "RAG not available"
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embed", json={
            "model": EMBED_MODEL, "input": [query]
        }, timeout=30)
        q_emb = r.json().get("embeddings", [[]])[0]
        if not q_emb: return "No embedding for query"
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
