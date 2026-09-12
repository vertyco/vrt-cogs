import logging
import math
import re
from collections import Counter

log = logging.getLogger("red.vrt.assistant.keyword_index")

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


class KeywordIndex:
    """BM25 index over memory text, used when no embedding can be made for the query.

    Scores are normalised so the best hit is 1.0; documents sharing no term with the query are dropped.
    """

    def __init__(self) -> None:
        self.doc_terms: dict[str, Counter] = {}
        self.doc_lengths: dict[str, int] = {}
        self.doc_freq: Counter = Counter()
        self.avg_length: float = 0.0

    def build(self, docs: dict[str, str]) -> None:
        self.doc_terms = {name: Counter(tokenize(text)) for name, text in docs.items()}
        self.doc_lengths = {name: sum(terms.values()) for name, terms in self.doc_terms.items()}
        self.doc_freq = Counter()
        for terms in self.doc_terms.values():
            self.doc_freq.update(terms.keys())
        self.avg_length = (sum(self.doc_lengths.values()) / len(self.doc_lengths)) if self.doc_lengths else 0.0

    def idf(self, term: str) -> float:
        n = len(self.doc_terms)
        df = self.doc_freq.get(term, 0)
        return math.log((n - df + 0.5) / (df + 0.5) + 1)

    def score(self, name: str, query_terms: list[str]) -> float:
        terms = self.doc_terms[name]
        length = self.doc_lengths[name]
        total = 0.0
        for term in query_terms:
            tf = terms.get(term, 0)
            if not tf:
                continue
            denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * length / self.avg_length)
            total += self.idf(term) * tf * (BM25_K1 + 1) / denom
        return total

    def search(self, query: str, top_n: int) -> list[tuple[str, float]]:
        query_terms = list(dict.fromkeys(tokenize(query)))
        if not query_terms or not self.doc_terms or top_n <= 0:
            return []
        scored = [(name, self.score(name, query_terms)) for name in self.doc_terms]
        scored = [(name, score) for name, score in scored if score > 0]
        if not scored:
            return []
        scored.sort(key=lambda item: item[1], reverse=True)
        best = scored[0][1]
        return [(name, score / best) for name, score in scored[:top_n]]
