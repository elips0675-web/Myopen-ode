"""Stage 42: storage abstractions (swap FAISS/SQLite behind interfaces).

RAGStore — vector/full-text search over the workspace (default impl wraps
the rag module's hybrid BM25+FAISS search).
KVStore  — generic key-value / SQL storage with execute + query (default
impl wraps SQLite; sessions use it too).
"""

import os
import sqlite3
import threading

from . import container


class RAGStore:
    """Interface for workspace search. Subclass and register('rag') to swap
    in a different index (e.g. an external vector DB)."""

    def search(self, query, top_k=5, max_files=3):
        raise NotImplementedError

    def status(self):
        return {"chunks": 0, "embeddings": 0}


class RagAdapter(RAGStore):
    """Default: delegates to the in-process rag module (hybrid BM25 + FAISS)."""

    def __init__(self, rag_module):
        self._rag = rag_module

    def search(self, query, top_k=5, max_files=3):
        return self._rag.search(query, top_k=top_k, max_files=max_files)

    def status(self):
        try:
            return {
                "chunks": self._rag.get_index_size() if hasattr(self._rag, "get_index_size") else 0,
                "embeddings": 0,
            }
        except Exception:
            return {"chunks": 0, "embeddings": 0}


class KVStore:
    """Interface for the persistent session/state store. Default impl is
    SQLite; swap in Redis/JSON by registering('sessions_db')."""

    def execute(self, sql, params=()):
        """Run a write (INSERT/UPDATE/DELETE). Returns rowcount."""
        raise NotImplementedError

    def query(self, sql, params=()):
        """Run a read (SELECT). Returns list of sqlite3.Row-like objects."""
        raise NotImplementedError


class SqliteKVStore(KVStore):
    """Thread-safe SQLite-backed store. Creates the file + parent dirs."""

    def __init__(self, db_path):
        self._path = str(db_path)
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.rowcount

    def query(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self):
        with self._lock:
            self._conn.close()


def default_rag():
    return RagAdapter(_import_rag())


def _import_rag():
    import rag as _rag
    return _rag


def init_defaults():
    """Register stage-42 defaults (overridable by agent.py after startup)."""
    if not container.has("rag"):
        container.register("rag", default_rag)
