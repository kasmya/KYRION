"""
### Task 10: Recommendation System (FastAPI + scikit-learn)

A hybrid recommendation service combining collaborative filtering
(truncated SVD over a user-item matrix) with content-based filtering
(TF-IDF over item descriptions), exposed via a REST API.

Requirements:
    pip install fastapi "uvicorn[standard]" scikit-learn pandas numpy

Run:
    uvicorn 10_recommendation_system:app --host 0.0.0.0 --port 8004
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("recommendation_system")

# --- Example in-memory dataset. Replace with a real DB-backed source. ---
RATINGS_DATA = pd.DataFrame(
    [
        {"user_id": 1, "item_id": 101, "rating": 5},
        {"user_id": 1, "item_id": 102, "rating": 3},
        {"user_id": 2, "item_id": 101, "rating": 4},
        {"user_id": 2, "item_id": 103, "rating": 5},
        {"user_id": 3, "item_id": 102, "rating": 2},
        {"user_id": 3, "item_id": 104, "rating": 4},
        {"user_id": 4, "item_id": 101, "rating": 5},
        {"user_id": 4, "item_id": 104, "rating": 5},
    ]
)

ITEMS_DATA = pd.DataFrame(
    [
        {"item_id": 101, "title": "Wireless Headphones", "description": "noise cancelling wireless bluetooth audio headphones"},
        {"item_id": 102, "title": "Running Shoes", "description": "lightweight breathable running shoes for athletes"},
        {"item_id": 103, "title": "Bluetooth Speaker", "description": "portable wireless bluetooth speaker with deep bass"},
        {"item_id": 104, "title": "Yoga Mat", "description": "non-slip eco-friendly yoga and exercise mat"},
    ]
)

SVD_COMPONENTS = 2


class RecommendationEngine:
    """Encapsulates collaborative, content-based, and hybrid recommendation logic."""

    def __init__(self, ratings: pd.DataFrame, items: pd.DataFrame) -> None:
        self.ratings = ratings
        self.items = items.set_index("item_id")
        self._build_collaborative_model()
        self._build_content_model()

    def _build_collaborative_model(self) -> None:
        """Builds a user-item matrix and fits a truncated SVD collaborative filter."""
        self.user_item_matrix = self.ratings.pivot_table(
            index="user_id", columns="item_id", values="rating", fill_value=0
        )

        n_components = min(SVD_COMPONENTS, min(self.user_item_matrix.shape) - 1)
        n_components = max(n_components, 1)

        self.svd = TruncatedSVD(n_components=n_components, random_state=42)
        self.user_factors = self.svd.fit_transform(self.user_item_matrix.values)
        self.item_factors = self.svd.components_.T
        self.reconstructed = np.dot(self.user_factors, self.item_factors.T)
        logger.info(
            "Fitted collaborative filter with %d component(s) over %s user-item matrix",
            n_components,
            self.user_item_matrix.shape,
        )

    def _build_content_model(self) -> None:
        """Builds a TF-IDF representation of item descriptions for content-based filtering."""
        self.vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = self.vectorizer.fit_transform(self.items["description"])
        self.content_similarity = cosine_similarity(tfidf_matrix)
        self.item_id_to_index = {item_id: idx for idx, item_id in enumerate(self.items.index)}
        logger.info("Fitted content-based TF-IDF model over %d item(s)", len(self.items))

    def collaborative_recommendations(self, user_id: int, top_n: int = 5) -> List[Dict]:
        """Recommends items for a user based on reconstructed SVD scores."""
        if user_id not in self.user_item_matrix.index:
            raise ValueError(f"unknown user_id: {user_id}")

        user_idx = self.user_item_matrix.index.get_loc(user_id)
        scores = self.reconstructed[user_idx]
        already_rated = set(
            self.ratings.loc[self.ratings["user_id"] == user_id, "item_id"]
        )

        item_ids = self.user_item_matrix.columns
        candidates = [
            (item_id, score)
            for item_id, score in zip(item_ids, scores)
            if item_id not in already_rated
        ]
        candidates.sort(key=lambda pair: pair[1], reverse=True)

        return [
            {"item_id": item_id, "title": self.items.loc[item_id, "title"], "score": round(float(score), 4)}
            for item_id, score in candidates[:top_n]
        ]

    def content_based_recommendations(self, item_id: int, top_n: int = 5) -> List[Dict]:
        """Recommends items similar in content/description to a given item."""
        if item_id not in self.item_id_to_index:
            raise ValueError(f"unknown item_id: {item_id}")

        idx = self.item_id_to_index[item_id]
        similarities = list(enumerate(self.content_similarity[idx]))
        similarities = [(i, score) for i, score in similarities if i != idx]
        similarities.sort(key=lambda pair: pair[1], reverse=True)

        results = []
        for i, score in similarities[:top_n]:
            similar_item_id = self.items.index[i]
            results.append(
                {
                    "item_id": int(similar_item_id),
                    "title": self.items.loc[similar_item_id, "title"],
                    "similarity": round(float(score), 4),
                }
            )
        return results

    def hybrid_recommendations(
        self, user_id: int, top_n: int = 5, collab_weight: float = 0.6
    ) -> List[Dict]:
        """Blends collaborative and content-based scores into a single ranked list.

        For each candidate item, combines its normalized collaborative score with
        the average content similarity to items the user has already rated highly.
        """
        if user_id not in self.user_item_matrix.index:
            raise ValueError(f"unknown user_id: {user_id}")

        liked_items = self.ratings[
            (self.ratings["user_id"] == user_id) & (self.ratings["rating"] >= 4)
        ]["item_id"].tolist()

        collab_candidates = self.collaborative_recommendations(user_id, top_n=len(self.items))
        collab_scores = {c["item_id"]: c["score"] for c in collab_candidates}

        max_score = max(collab_scores.values()) if collab_scores else 1.0
        min_score = min(collab_scores.values()) if collab_scores else 0.0
        score_range = (max_score - min_score) or 1.0

        blended = []
        for item_id, collab_score in collab_scores.items():
            normalized_collab = (collab_score - min_score) / score_range

            if liked_items:
                content_scores = []
                for liked_id in liked_items:
                    if liked_id in self.item_id_to_index and item_id in self.item_id_to_index:
                        i, j = self.item_id_to_index[liked_id], self.item_id_to_index[item_id]
                        content_scores.append(self.content_similarity[i][j])
                content_score = float(np.mean(content_scores)) if content_scores else 0.0
            else:
                content_score = 0.0

            final_score = collab_weight * normalized_collab + (1 - collab_weight) * content_score
            blended.append(
                {
                    "item_id": item_id,
                    "title": self.items.loc[item_id, "title"],
                    "score": round(final_score, 4),
                }
            )

        blended.sort(key=lambda entry: entry["score"], reverse=True)
        return blended[:top_n]


engine: Optional[RecommendationEngine] = None
app = FastAPI(title="Recommendation System API")


class RecommendationResponse(BaseModel):
    user_id: Optional[int] = None
    item_id: Optional[int] = None
    recommendations: List[Dict]


@app.on_event("startup")
def on_startup() -> None:
    global engine
    engine = RecommendationEngine(RATINGS_DATA, ITEMS_DATA)
    logger.info("Recommendation engine initialized")


@app.get("/recommendations/collaborative/{user_id}", response_model=RecommendationResponse)
def get_collaborative(user_id: int, top_n: int = 5):
    """Returns collaborative-filtering recommendations for a user."""
    assert engine is not None
    try:
        recs = engine.collaborative_recommendations(user_id, top_n)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RecommendationResponse(user_id=user_id, recommendations=recs)


@app.get("/recommendations/content/{item_id}", response_model=RecommendationResponse)
def get_content_based(item_id: int, top_n: int = 5):
    """Returns content-based recommendations similar to a given item."""
    assert engine is not None
    try:
        recs = engine.content_based_recommendations(item_id, top_n)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RecommendationResponse(item_id=item_id, recommendations=recs)


@app.get("/recommendations/hybrid/{user_id}", response_model=RecommendationResponse)
def get_hybrid(user_id: int, top_n: int = 5, collab_weight: float = 0.6):
    """Returns hybrid (collaborative + content-based) recommendations for a user."""
    assert engine is not None
    if not 0 <= collab_weight <= 1:
        raise HTTPException(status_code=400, detail="collab_weight must be between 0 and 1")
    try:
        recs = engine.hybrid_recommendations(user_id, top_n, collab_weight)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RecommendationResponse(user_id=user_id, recommendations=recs)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
