import math
import re
import json
import gzip
from pathlib import Path
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Optional, Iterable, List, Tuple, Dict, Any

from .base import BaseRetriever

# -----------------------
# Fast token & n-gram cache
# -----------------------

_TOK_RE = re.compile(r"\w+")


@lru_cache(maxsize=500_000)
def _toks_cached(s: str) -> List[str]:
    return [t.lower() for t in _TOK_RE.findall(s)]


@lru_cache(maxsize=500_000)
def _ngrams_cached(s: str, n: int = 3):
    xs = _toks_cached(s)
    return frozenset(tuple(xs[i:i + n]) for i in range(max(0, len(xs) - n + 1)))


def jaccard_ngrams(a: str, b: str, n: int = 3) -> float:
    A, B = _ngrams_cached(a, n), _ngrams_cached(b, n)
    if not A and not B:
        return 1.0
    inter = len(A & B)
    return inter / max(1, len(A) + len(B) - inter)


# -----------------------
# In-memory BM25 + temporal + fast dedup
# -----------------------

class InMemoryBM25Temporal(BaseRetriever):
    """
    Speedups vs. previous:
      - Inverted index: postings[token] -> list[(doc_id, tf)]
      - Precomputed idf[token] and per-doc norm[doc_id]
      - O(1) avgdl maintenance
      - Dedup candidates from tri->docs inverted index (no full scan)
    """

    def __init__(self, k1=1.5, b=0.75, dedup_threshold=0.8, dedup_sim_fn=jaccard_ngrams, replace_on_dedup=True):
        self.k1, self.b = k1, b
        self.dedup_threshold = dedup_threshold
        self.dedup_sim_fn = dedup_sim_fn
        self.replace_on_dedup = replace_on_dedup

        self.docs: List[Dict[str, Any]] = []
        self.N: int = 0

        # BM25 structures
        self.df: Counter = Counter()
        self.idf: Dict[str, float] = {}
        self.postings: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self.doc_norm: List[float] = []
        self.total_len: int = 0
        self.avgdl: float = 0.0

        # Dedup structures
        self.tri_to_docs: Dict[tuple, List[int]] = defaultdict(list)

    # ---- utilities ----

    def _toks(self, s: str) -> List[str]:
        return _toks_cached(s)

    def _recompute_idf_for(self, token: str):
        df = self.df.get(token, 0)
        N = self.N
        if df == 0:
            self.idf.pop(token, None)
        else:
            self.idf[token] = math.log(1.0 + (N - df + 0.5) / (df + 0.5))

    def _update_avgdl_and_norm(self, doc_id: Optional[int] = None):
        self.avgdl = (self.total_len / self.N) if self.N else 0.0
        if doc_id is not None and self.N:
            dlen = self.docs[doc_id]["len"]
            self.doc_norm[doc_id] = self.k1 * (1.0 - self.b + self.b * (dlen / self.avgdl if self.avgdl > 0 else 0.0))

    def reset(self):
        self.__init__(k1=self.k1, b=self.b, dedup_threshold=self.dedup_threshold, dedup_sim_fn=self.dedup_sim_fn)

    # ---- add / replace helpers ----

    def _index_new_doc(self, doc_id: int):
        d = self.docs[doc_id]
        for w, tfw in d["tf"].items():
            if tfw <= 0:
                continue
        for w in d["uniq_toks"]:
            self.df[w] += 1
            self._recompute_idf_for(w)
        for w, tfw in d["tf"].items():
            self.postings[w].append((doc_id, tfw))
        for tri in d["tri"]:
            self.tri_to_docs[tri].append(doc_id)
        if doc_id == len(self.doc_norm):
            self.doc_norm.append(0.0)
        self._update_avgdl_and_norm(doc_id)

    def _unindex_doc(self, doc_id: int):
        d = self.docs[doc_id]
        for w, tfw in d["tf"].items():
            lst = self.postings.get(w)
            if not lst:
                continue
            self.postings[w] = [(i, t) for (i, t) in lst if i != doc_id]
            if not self.postings[w]:
                del self.postings[w]
        for w in d["uniq_toks"]:
            self.df[w] -= 1
            if self.df[w] <= 0:
                self.df.pop(w, None)
                self.idf.pop(w, None)
            else:
                self._recompute_idf_for(w)
        for tri in d["tri"]:
            lst = self.tri_to_docs.get(tri)
            if lst:
                self.tri_to_docs[tri] = [i for i in lst if i != doc_id]
                if not self.tri_to_docs[tri]:
                    del self.tri_to_docs[tri]

    # ---- API ----

    def add(self, text: str, *, event_ts: int, visible_after_ts: Optional[int] = None,
            namespace: str = "train", metadata: Optional[dict] = None):
        if visible_after_ts is None:
            visible_after_ts = event_ts

        toks = self._toks(text)
        tf = Counter(toks)
        tri = _ngrams_cached(text, 3)
        uniq_toks = set(tf.keys())
        dlen = len(toks)

        cand_docs = set()
        for tri_g in tri:
            for doc_id in self.tri_to_docs.get(tri_g, ()):
                if self.docs[doc_id]["namespace"] == namespace:
                    cand_docs.add(doc_id)

        for doc_id in cand_docs:
            existing = self.docs[doc_id]
            A, B = tri, existing["tri"]
            inter = len(A & B)
            sim = inter / max(1, len(A) + len(B) - inter)
            if sim >= self.dedup_threshold:
                if event_ts >= existing["event_ts"]:
                    self._unindex_doc(doc_id)
                    self.total_len -= existing["len"]
                    self.docs[doc_id] = {
                        "text": text, "toks": toks, "tf": tf, "uniq_toks": uniq_toks,
                        "tri": tri, "len": dlen,
                        "event_ts": int(event_ts), "visible_after_ts": int(visible_after_ts),
                        "namespace": namespace, "meta": metadata or {},
                    }
                    self.total_len += dlen
                    self._index_new_doc(doc_id)
                return

        doc = {
            "text": text, "toks": toks, "tf": tf, "uniq_toks": uniq_toks,
            "tri": tri, "len": dlen,
            "event_ts": int(event_ts), "visible_after_ts": int(visible_after_ts),
            "namespace": namespace, "meta": metadata or {},
        }
        self.docs.append(doc)
        self.N += 1
        self.total_len += dlen
        new_id = self.N - 1
        self._index_new_doc(new_id)

    def query(self, text: str, *, k: int, cutoff_ts: int,
              namespaces: Optional[Iterable[str]] = None,
              time_decay_lambda: Optional[float] = None):
        if self.N == 0:
            return []

        q_tokens = _toks_cached(text)
        if not q_tokens:
            return []

        ns = set(namespaces) if namespaces else None

        q_uniq = []
        seen = set()
        for w in q_tokens:
            if w not in seen:
                seen.add(w)
                if self.df.get(w, 0) > 0:
                    q_uniq.append(w)

        if not q_uniq:
            return []

        scores: Dict[int, float] = {}

        for w in q_uniq:
            idf = self.idf.get(w)
            if idf is None:
                self._recompute_idf_for(w)
                idf = self.idf.get(w)
                if idf is None:
                    continue
            plist = self.postings.get(w)
            if not plist:
                continue
            for doc_id, tfw in plist:
                d = self.docs[doc_id]
                if d["event_ts"] > cutoff_ts or d["visible_after_ts"] > cutoff_ts:
                    continue
                if ns and d["namespace"] not in ns:
                    continue
                denom = tfw + self.doc_norm[doc_id]
                s = idf * (tfw * (self.k1 + 1.0)) / (denom if denom > 1e-12 else 1e-12)
                scores[doc_id] = scores.get(doc_id, 0.0) + s

        if not scores:
            return []

        if time_decay_lambda:
            lam = float(time_decay_lambda)
            for doc_id, s in list(scores.items()):
                age_seconds = max(0, cutoff_ts - self.docs[doc_id]["event_ts"])
                age_days = age_seconds / 86400.0
                scores[doc_id] = s * math.exp(-lam * age_days)

        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
        out = []
        for doc_id, s in top:
            d = self.docs[doc_id]
            out.append({
                "text": d["text"],
                "meta": d["meta"],
                "score": float(s),
                "event_ts": d["event_ts"],
            })
        return out

    def save_checkpoint(self, checkpoint_path: str):
        checkpoint_path = Path(checkpoint_path)

        if checkpoint_path.is_dir() or (not checkpoint_path.suffix):
            checkpoint_path = checkpoint_path / "retriever.json.gz"

        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            "config": {
                "k1": self.k1,
                "b": self.b,
                "dedup_threshold": self.dedup_threshold,
            },
            "docs": [
                {
                    "text": doc["text"],
                    "toks": doc["toks"],
                    "tf": dict(doc["tf"]),
                    "uniq_toks": list(doc["uniq_toks"]),
                    "tri": [list(t) for t in doc["tri"]],
                    "len": doc["len"],
                    "event_ts": doc["event_ts"],
                    "visible_after_ts": doc["visible_after_ts"],
                    "namespace": doc["namespace"],
                    "meta": doc["meta"],
                }
                for doc in self.docs
            ],
            "N": self.N,
            "total_len": self.total_len,
        }

        with gzip.open(checkpoint_path, 'wt', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2)

    def load_checkpoint(self, checkpoint_path: str):
        checkpoint_path = Path(checkpoint_path)

        if checkpoint_path.is_dir():
            checkpoint_path = checkpoint_path / "retriever.json.gz"

        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        with gzip.open(checkpoint_path, 'rt', encoding='utf-8') as f:
            checkpoint_data = json.load(f)

        config = checkpoint_data["config"]
        self.__init__(
            k1=config["k1"],
            b=config["b"],
            dedup_threshold=config["dedup_threshold"],
            dedup_sim_fn=self.dedup_sim_fn
        )

        self.docs = []
        for doc_data in checkpoint_data["docs"]:
            doc = {
                "text": doc_data["text"],
                "toks": doc_data["toks"],
                "tf": Counter(doc_data["tf"]),
                "uniq_toks": set(doc_data["uniq_toks"]),
                "tri": frozenset(tuple(t) for t in doc_data["tri"]),
                "len": doc_data["len"],
                "event_ts": doc_data["event_ts"],
                "visible_after_ts": doc_data["visible_after_ts"],
                "namespace": doc_data["namespace"],
                "meta": doc_data["meta"],
            }
            self.docs.append(doc)

        self.N = len(self.docs)
        self.total_len = checkpoint_data["total_len"]

        for doc_id in range(self.N):
            self._index_new_doc(doc_id)


# -----------------------
# MMR with precomputed tri-grams (fast path)
# -----------------------

def mmr_select(items: List[Tuple[str, float, Any]], top_m: int, alpha: float = 0.7):
    """
    items: list of (text, utility, payload)
    Optimized for Jaccard on tri-grams:
      - Precompute tri-gram sets once.
      - Work over indices to reduce object traffic.
    """
    if not items:
        return []

    tri_by_idx = {i: _ngrams_cached(items[i][0], 3) for i in range(len(items))}

    def sim_idx(i: int, j: int) -> float:
        A, B = tri_by_idx[i], tri_by_idx[j]
        inter = len(A & B)
        return inter / max(1, len(A) + len(B) - inter)

    order = sorted(range(len(items)), key=lambda i: items[i][1], reverse=True)
    sel = [order.pop(0)]

    while order and len(sel) < top_m:
        best, best_score = None, float("-inf")
        for j in order:
            sim = max(sim_idx(j, i) for i in sel)
            score = alpha * items[j][1] - (1 - alpha) * sim
            if score > best_score:
                best, best_score = j, score
        order.remove(best)
        sel.append(best)

    return [items[i] for i in sel]
