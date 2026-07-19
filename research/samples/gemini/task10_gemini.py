"""
Task 10: FastAPI Hybrid Machine Learning Suggestion Service
Features: SVD collaborative prediction modeling, TF-IDF cosine-similarity calculations, hybrid synthesis logic.
Requires: fastapi, uvicorn, scikit-learn, pandas, surprise, pydantic
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
import logging
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from surprise import SVD, Dataset, Reader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Hybrid Predictive Recommendation Inference System", version="1.0.0")

# --- Mock Catalog Matrix Data Initializations ---
# In production, these datasets map live relational updates from data lake operations
catalog_items = pd.DataFrame([
    {"item_id": 101, "title": "Introduction to AI Core Algorithms", "metadata_tags": "machine learning python coding artificial intelligence"},
    {"item_id": 102, "title": "Advanced Neural Networks Architecture", "metadata_tags": "deep learning ai mathematical modeling networks python"},
    {"item_id": 103, "title": "Corporate Financial Planning Projections", "metadata_tags": "finance excel ledger analytics asset forecasting"},
    {"item_id": 104, "title": "Data Engineering Patterns and Warehouses", "metadata_tags": "sql database scale etl airflow pipeline big data"},
    {"item_id": 105, "title": "Automated Systems Integration Handbooks", "metadata_tags": "python api systems engineering devops microservices"}
])

historical_user_reviews = pd.DataFrame([
    {"user_id": "U1", "item_id": 101, "rating": 5.0},
    {"user_id": "U1", "item_id": 102, "rating": 4.5},
    {"user_id": "U2", "item_id": 103, "rating": 4.8},
    {"user_id": "U3", "item_id": 101, "rating": 4.0},
    {"user_id": "U3", "item_id": 104, "rating": 5.0},
    {"user_id": "U4", "item_id": 105, "rating": 4.2}
])

# --- Model Engineering Layer Pipelines ---

class HybridRecommendationEngine:
    """Manages training lifecycles over TF-IDF space vectors and Matrix Factorization frameworks."""
    
    def __init__(self) -> None:
        self.tfidf_matrix: Optional[np.ndarray] = None
        self.tfidf_vectorizer = TfidfVectorizer(stop_words='english')
        self.svd_model = SVD(n_factors=20, random_state=42)
        self.retrain_system_models()

    def retrain_system_models(self) -> None:
        """Trains both algorithmic model layers simultaneously."""
        logger.info("Initializing Collaborative Filtering matrix decomposition training runs.")
        # Surprise SVD matrix ingestion setup
        reader = Reader(rating_scale=(1.0, 5.0))
        dataset_wrapper = Dataset.load_from_df(historical_user_reviews[['user_id', 'item_id', 'rating']], reader)
        training_set = dataset_wrapper.build_full_trainset()
        self.svd_model.fit(training_set)

        logger.info("Assembling Content-based spatial text vector indexing profiles.")
        # TF-IDF Cosine Similarity Matrix Setup
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(catalog_items['metadata_tags']).toarray()
        logger.info("Recommendation core computational vectors built successfully.")

    def compute_hybrid_inference(self, user_id: str, target_item_id: int, weight_collaborative: float = 0.6) -> float:
        """Synthesizes implicit content similarities alongside spatial SVD matrices to project score weights."""
        # 1. Compute Collaborative Scoring Metric Component
        predicted_svd_score = self.svd_model.predict(user_id, target_item_id).est

        # 2. Compute Content Similarity Component Tracking
        try:
            target_idx = catalog_items[catalog_items['item_id'] == target_item_id].index[0]
            # Extract historical items highly rated by this individual consumer
            user_positive_history = historical_user_reviews[
                (historical_user_reviews['user_id'] == user_id) & (historical_user_reviews['rating'] >= 4.0)
            ]['item_id'].tolist()
            
            if user_positive_history and self.tfidf_matrix is not None:
                history_indices = catalog_items[catalog_items['item_id'].isin(user_positive_history)].index.tolist()
                similarity_vectors = cosine_similarity([self.tfidf_matrix[target_idx]], self.tfidf_matrix[history_indices])
                content_score_component = float(np.mean(similarity_vectors)) * 4.0 + 1.0 # Rescale to matching 1-5 matrix systems
            else:
                content_score_component = 3.0 # Neutral anchor fallback baseline parameter if user profiles lack history logs
        except IndexError:
            content_score_component = 3.0

        # Weighted interpolation algorithm calculations
        final_hybrid_score = (weight_collaborative * predicted_svd_score) + ((1.0 - weight_collaborative) * content_score_component)
        return float(final_hybrid_score)

# Instantiate operational engine
engine_pipeline = HybridRecommendationEngine()

# --- Pydantic API Models ---

class InferenceQuery(BaseModel):
    user_id: str = Field(..., example="U1")
    total_suggestions_requested: int = Field(5, ge=1, le=20)

class ProductRecommendation(BaseModel):
    item_id: int
    title: str
    projected_match_score: float

class InferenceOutputEnvelope(BaseModel):
    user_id: str
    recommendations: List[ProductRecommendation]

# --- REST Inference Routers ---

@app.post("/recommendations", response_model=InferenceOutputEnvelope)
def extract_hybrid_user_recommendations(query: InferenceQuery) -> Any:
    """Calculates predictions across item matrices, sorting by highest hybrid confidence score fields."""
    all_item_ids = catalog_items['item_id'].unique().tolist()
    
    scoring_ledger: List[ProductRecommendation] = []
    
    for current_item_id in all_item_ids:
        try:
            predicted_rank = engine_pipeline.compute_hybrid_inference(query.user_id, current_item_id)
            title_string = catalog_items[catalog_items['item_id'] == current_item_id]['title'].values[0]
            
            scoring_ledger.append(ProductRecommendation(
                item_id=current_item_id,
                title=title_string,
                projected_match_score=round(predicted_rank, 3)
            ))
        except Exception as inner_calc_err:
            logger.error(f"Error evaluating internal hybrid processing vectors for element {current_item_id}: {inner_calc_err}")
            continue

    # Sort results to present highest quality item matches first
    scoring_ledger.sort(key=lambda record: record.projected_match_score, reverse=True)
    sliced_output = scoring_ledger[:query.total_suggestions_requested]
    
    return {
        "user_id": query.user_id,
        "recommendations": sliced_output
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
