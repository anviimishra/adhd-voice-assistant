import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict


class TabRetriever:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.tabs: List[Dict] = []
        self.vectors: List[Counter] = []
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as fh:
                    self.tabs = json.load(fh)
            except Exception:
                self.tabs = []
        else:
            self.tabs = []
        self._vectorize_all()

    def _vectorize_all(self):
        self.vectors = [self._vectorize_tab(tab) for tab in self.tabs]

    def has_tabs(self) -> bool:
        return len(self.tabs) > 0

    def save_tabs(self, tabs: List[Dict]):
        sanitized = []
        for tab in tabs or []:
            sanitized.append({
                "title": (tab.get("title") or "")[:200],
                "url": tab.get("url") or "",
                "content": (tab.get("content") or "")[:6000]
            })
        with open(self.storage_path, "w", encoding="utf-8") as fh:
            json.dump(sanitized, fh)
        self.tabs = sanitized
        self._vectorize_all()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9]{3,}", (text or "").lower())

    def _vectorize_tab(self, tab: Dict) -> Counter:
        text = f"{tab.get('title', '')} {tab.get('content', '')}"
        return Counter(self._tokenize(text))

    def _vectorize_query(self, query: str) -> Counter:
        return Counter(self._tokenize(query))

    def _cosine_similarity(self, vec_a: Counter, vec_b: Counter) -> float:
        if not vec_a or not vec_b:
            return 0.0
        dot = sum(vec_a[token] * vec_b.get(token, 0) for token in vec_a)
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if not norm_a or not norm_b:
            return 0.0
        return dot / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 3, min_score: float = 0.05) -> List[Dict]:
        query_vec = self._vectorize_query(query)
        results = []
        for index, doc_vec in enumerate(self.vectors):
            score = self._cosine_similarity(query_vec, doc_vec)
            if score >= min_score:
                tab = self.tabs[index]
                snippet = (tab.get("content") or "")[:320]
                results.append({
                    "title": tab.get("title") or "",
                    "url": tab.get("url") or "",
                    "snippet": snippet,
                    "score": round(score, 4)
                })
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]


_storage_path = Path(__file__).resolve().parent / "tab_cache.json"
_retriever = TabRetriever(_storage_path)


def sync_tabs_snapshot(tabs: List[Dict]):
    _retriever.save_tabs(tabs)


def retriever_has_tabs() -> bool:
    return _retriever.has_tabs()


def group_tabs_for_subtasks(task_name: str, subtask_names: List[str], top_k: int = 3) -> List[Dict]:
    groups = []
    if not retriever_has_tabs():
        return groups

    for name in subtask_names:
        combined_query = f"{task_name} {name}".strip()
        tabs = _retriever.search(combined_query, top_k=top_k)
        groups.append({
            "subtask": name,
            "tabs": tabs,
            "matchCount": len(tabs)
        })
    return groups
