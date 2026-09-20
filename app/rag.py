"""RAG engine — hybrid retrieval (local vectors + keyword, RRF fusion),
calibrated confidence gate, tenant-first scope for college data."""
import math
import re
from collections import Counter

from .config import SETTINGS
from .db import KbChunk, SessionLocal

EMB_DIM = 4096
STOP = set("the a an and or of to in for on with is are was were be been it its this that as at by from your you we our their they he she i not no do does did will can could should would may might must have has had than then so if but about into over under more most other some such only own same too very s t just don now".split())


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 1]


def _bigrams(tokens: list[str]) -> list[str]:
    return [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]


def local_embed(text: str) -> list[float]:
    counts = Counter(_tokens(text) + _bigrams(_tokens(text)))
    v = [0.0] * EMB_DIM
    for term, tf in counts.items():
        idx = int.from_bytes(term.encode()[:8], "little") % EMB_DIM
        v[idx] += 1.0 + math.log(tf)
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def embed(text: str) -> list[float]:
    if SETTINGS.embedding_provider == "openai" and SETTINGS.openai_api_key:
        try:
            import httpx
            r = httpx.post("https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {SETTINGS.openai_api_key}"},
                json={"model": SETTINGS.openai_embed_model, "input": text[:8000]}, timeout=30)
            r.raise_for_status()
            return r.json()["data"][0]["embedding"]
        except Exception:
            pass
    return local_embed(text)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def chunk_text(content: str, target_words: int = 170, overlap: int = 30) -> list[str]:
    paras = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for para in paras:
        if len(cur.split()) + len(para.split()) <= target_words:
            cur = (cur + " " + para).strip()
        else:
            if cur:
                chunks.append(cur)
            if len(para.split()) <= target_words:
                cur = para
            else:
                sents, s = [], ""
                for sent in re.split(r"(?<=[.!?]) ", para):
                    if len(s.split()) + len(sent.split()) <= target_words:
                        s = (s + " " + sent).strip()
                    else:
                        if s:
                            sents.append(s)
                        s = sent
                if s:
                    sents.append(s)
                chunks.extend(sents)
                cur = ""
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        out.append((" ".join(chunks[i - 1].split()[-overlap:]) + " " + c) if (i > 0 and overlap) else c)
    return out


def ingest(content: str, title: str, section: str = "", scope: str = "global",
           college_id: int | None = None, db=None):
    own = db is None
    if own:
        db = SessionLocal()
    n = 0
    for piece in chunk_text(content):
        db.add(KbChunk(scope=scope, college_id=college_id, title=title,
                       section=section, content=piece, vec=embed(piece)))
        n += 1
    if own:
        db.commit()
        db.close()
    return n


def _is_confident(hits) -> bool:
    if not hits:
        return False
    c, fused, vec, lex = hits[0]
    return (vec >= 0.16) or (lex >= 0.22)


def retrieve(query: str, college_id: int | None, k: int = 5, db=None, scope: str = "all"):
    """scope='tenant_first': college data wins for parent-facing answers,
    global doctrine as fallback. scope='all': mixed (dashboard/KB search)."""
    own = db is None
    if own:
        db = SessionLocal()
    chunks = db.query(KbChunk).filter(
        (KbChunk.scope == "global") | (KbChunk.college_id == college_id)).all()
    if own:
        db.close()
    if not chunks:
        return []

    def _score_pool(pool):
        if not pool:
            return []
        qv = embed(query)
        q_terms = set(_tokens(query))
        vec_scores, lex_scores = [], []
        for c in pool:
            vec_scores.append(cosine(qv, c.vec) if c.vec else 0.0)
            c_terms = set(_tokens(c.content + " " + c.title))
            lex_scores.append(len(q_terms & c_terms) / (len(q_terms) or 1))

        def rrf(rank_lists, const=60):
            scores = {}
            for ranks in rank_lists:
                order = sorted(range(len(ranks)), key=lambda i: ranks[i], reverse=True)
                for pos, idx in enumerate(order):
                    scores[idx] = scores.get(idx, 0.0) + 1.0 / (const + pos + 1)
            return scores

        fused = rrf([vec_scores, lex_scores])
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [(pool[i], fused[i], vec_scores[i], lex_scores[i]) for i, _ in ranked]

    if scope == "tenant_first" and college_id:
        hits = _score_pool([c for c in chunks if c.college_id == college_id])
        if hits and _is_confident(hits):
            return hits
    return _score_pool(chunks)
