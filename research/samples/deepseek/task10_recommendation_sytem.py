"""
Hybrid Recommendation System with collaborative and content-based filtering.

Features:
- User-item collaborative filtering with SVD
- Content-based filtering with TF-IDF
- Hybrid recommendations
- REST API for recommendations
- Model persistence
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import LabelEncoder
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import svds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('recommendation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Recommendation System API",
    description="Hybrid recommendation system with collaborative and content-based filtering",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class UserPreferences(BaseModel):
    """User preferences for content-based recommendations."""
    user_id: str
    liked_items: List[str] = Field(default_factory=list)
    preferred_categories: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

class RecommendationRequest(BaseModel):
    """Recommendation request."""
    user_id: str
    n_recommendations: int = Field(default=10, ge=1, le=100)
    include_explanations: bool = Field(default=False)

class RecommendationItem(BaseModel):
    """Individual recommendation item."""
    item_id: str
    title: str
    score: float
    explanation: Optional[str] = None

class RecommendationResponse(BaseModel):
    """Recommendation response."""
    user_id: str
    recommendations: List[RecommendationItem]
    method: str
    generated_at: str

class CollaborativeFilter:
    """Collaborative filtering using matrix factorization (SVD)."""
    
    def __init__(self, n_factors: int = 50):
        """
        Initialize collaborative filter.
        
        Args:
            n_factors: Number of latent factors
        """
        self.n_factors = n_factors
        self.user_encoder = LabelEncoder()
        self.item_encoder = LabelEncoder()
        self.user_factors = None
        self.item_factors = None
        self.user_biases = None
        self.item_biases = None
        self.global_mean = None
        self.is_fitted = False
    
    def fit(self, ratings_df: pd.DataFrame) -> None:
        """
        Fit collaborative filtering model.
        
        Args:
            ratings_df: DataFrame with columns [user_id, item_id, rating]
        """
        try:
            logger.info("Fitting collaborative filtering model...")
            
            # Encode users and items
            users = self.user_encoder.fit_transform(ratings_df['user_id'])
            items = self.item_encoder.fit_transform(ratings_df['item_id'])
            ratings = ratings_df['rating'].values
            
            # Create user-item matrix
            n_users = len(self.user_encoder.classes_)
            n_items = len(self.item_encoder.classes_)
            
            matrix = np.zeros((n_users, n_items))
            for u, i, r in zip(users, items, ratings):
                matrix[u, i] = r
            
            # Compute global mean
            self.global_mean = np.mean(ratings)
            
            # Center the matrix
            matrix_centered = matrix - self.global_mean
            
            # Perform SVD
            U, sigma, Vt = svds(matrix_centered, k=self.n_factors)
            
            # Convert to diagonal matrix
            sigma = np.diag(sigma)
            
            # Compute user and item factors
            self.user_factors = U
            self.item_factors = Vt.T
            self.user_biases = np.zeros(n_users)
            self.item_biases = np.zeros(n_items)
            
            # Compute biases
            for i in range(n_users):
                user_ratings = matrix[i, :]
                rated = user_ratings > 0
                if np.any(rated):
                    self.user_biases[i] = np.mean(user_ratings[rated]) - self.global_mean
            
            for j in range(n_items):
                item_ratings = matrix[:, j]
                rated = item_ratings > 0
                if np.any(rated):
                    self.item_biases[j] = np.mean(item_ratings[rated]) - self.global_mean
            
            self.is_fitted = True
            logger.info(f"Collaborative filtering model fitted: {n_users} users, {n_items} items")
            
        except Exception as e:
            logger.error(f"Error fitting collaborative filter: {str(e)}", exc_info=True)
            raise
    
    def predict(self, user_id: str, item_ids: List[str]) -> np.ndarray:
        """
        Predict ratings for user-item pairs.
        
        Args:
            user_id: User identifier
            item_ids: List of item identifiers
            
        Returns:
            Array of predicted ratings
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted yet")
        
        try:
            user_idx = self.user_encoder.transform([user_id])[0]
            item_indices = self.item_encoder.transform(item_ids)
        except ValueError as e:
            # New user or item
            return np.full(len(item_ids), self.global_mean)
        
        # Compute predictions
        predictions = self.global_mean + self.user_biases[user_idx]
        
        for i, item_idx in enumerate(item_indices):
            predictions[i] += self.item_biases[item_idx]
            predictions[i] += np.dot(
                self.user_factors[user_idx, :],
                self.item_factors[item_idx, :]
            )
        
        return predictions
    
    def get_recommendations(
        self, user_id: str, n: int = 10, exclude_items: List[str] = None
    ) -> List[Tuple[str, float]]:
        """
        Get top-N recommendations for user.
        
        Args:
            user_id: User identifier
            n: Number of recommendations
            exclude_items: Items to exclude
            
        Returns:
            List of (item_id, score) tuples
        """
        if not self.is_fitted:
            return []
        
        exclude_items = set(exclude_items or [])
        all_items = [item for item in self.item_encoder.classes_ if item not in exclude_items]
        
        if not all_items:
            return []
        
        predictions = self.predict(user_id, all_items)
        
        # Get top N
        top_indices = np.argsort(predictions)[-n:][::-1]
        
        recommendations = [
            (all_items[i], float(predictions[i]))
            for i in top_indices
        ]
        
        return recommendations

class ContentBasedFilter:
    """Content-based filtering using TF-IDF."""
    
    def __init__(self):
        """Initialize content-based filter."""
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        self.item_features = None
        self.item_ids = None
        self.item_matrix = None
        self.is_fitted = False
    
    def fit(self, items_df: pd.DataFrame) -> None:
        """
        Fit content-based model.
        
        Args:
            items_df: DataFrame with columns [item_id, title, description, category, tags]
        """
        try:
            logger.info("Fitting content-based model...")
            
            self.item_ids = items_df['item_id'].tolist()
            
            # Combine features into text
            texts = []
            for _, item in items_df.iterrows():
                text = f"{item.get('title', '')} {item.get('description', '')} "
                text += f"{item.get('category', '')} {item.get('tags', '')}"
                texts.append(text.lower())
            
            # Create TF-IDF matrix
            self.item_matrix = self.vectorizer.fit_transform(texts)
            self.is_fitted = True
            
            logger.info(f"Content-based model fitted with {len(texts)} items")
            
        except Exception as e:
            logger.error(f"Error fitting content-based model: {str(e)}", exc_info=True)
            raise
    
    def get_similar_items(
        self, item_id: str, n: int = 10, exclude_items: List[str] = None
    ) -> List[Tuple[str, float]]:
        """
        Get similar items to a given item.
        
        Args:
            item_id: Reference item
            n: Number of similar items
            exclude_items: Items to exclude
            
        Returns:
            List of (item_id, similarity_score) tuples
        """
        if not self.is_fitted:
            return []
        
        if item_id not in self.item_ids:
            return []
        
        exclude_items = set(exclude_items or [])
        exclude_items.add(item_id)
        
        item_idx = self.item_ids.index(item_id)
        item_vector = self.item_matrix[item_idx]
        
        # Compute similarities
        similarities = cosine_similarity(item_vector, self.item_matrix).flatten()
        
        # Get top N (excluding the item itself and excluded items)
        similar_indices = np.argsort(similarities)[::-1]
        
        recommendations = []
        for idx in similar_indices:
            if len(recommendations) >= n:
                break
            if self.item_ids[idx] not in exclude_items:
                recommendations.append(
                    (self.item_ids[idx], float(similarities[idx]))
                )
        
        return recommendations
    
    def get_user_recommendations(
        self, user_prefs: UserPreferences, n: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Get recommendations based on user preferences.
        
        Args:
            user_prefs: User preferences
            n: Number of recommendations
            
        Returns:
            List of (item_id, score) tuples
        """
        if not self.is_fitted:
            return []
        
        # Create user profile vector
        user_text = ' '.join(user_prefs.preferred_categories + user_prefs.keywords)
        
        if not user_text.strip():
            return []
        
        user_vector = self.vectorizer.transform([user_text.lower()])
        
        # Compute similarities
        similarities = cosine_similarity(user_vector, self.item_matrix).flatten()
        
        # Get top N
        top_indices = np.argsort(similarities)[-n:][::-1]
        
        recommendations = [
            (self.item_ids[i], float(similarities[i]))
            for i in top_indices
            if similarities[i] > 0
        ]
        
        return recommendations

class HybridRecommender:
    """Hybrid recommendation system combining multiple approaches."""
    
    def __init__(
        self,
        cf_weight: float = 0.5,
        cb_weight: float = 0.5
    ):
        """
        Initialize hybrid recommender.
        
        Args:
            cf_weight: Weight for collaborative filtering
            cb_weight: Weight for content-based filtering
        """
        self.cf_weight = cf_weight
        self.cb_weight = cb_weight
        self.cf_model = CollaborativeFilter()
        self.cb_model = ContentBasedFilter()
        self.items_metadata = {}
    
    def fit(self, ratings_df: pd.DataFrame, items_df: pd.DataFrame) -> None:
        """
        Fit all models.
        
        Args:
            ratings_df: Ratings data
            items_df: Items metadata
        """
        self.cf_model.fit(ratings_df)
        self.cb_model.fit(items_df)
        
        # Store items metadata
        for _, item in items_df.iterrows():
            self.items_metadata[item['item_id']] = {
                'title': item.get('title', ''),
                'category': item.get('category', ''),
                'description': item.get('description', '')
            }
        
        logger.info("Hybrid recommender fitted successfully")
    
    def get_recommendations(
        self,
        user_id: str,
        n: int = 10,
        user_prefs: Optional[UserPreferences] = None,
        exclude_items: List[str] = None
    ) -> List[RecommendationItem]:
        """
        Get hybrid recommendations.
        
        Args:
            user_id: User identifier
            n: Number of recommendations
            user_prefs: User preferences for content-based
            exclude_items: Items to exclude
            
        Returns:
            List of recommendation items
        """
        exclude_items = exclude_items or []
        
        # Get collaborative filtering recommendations
        cf_recs = self.cf_model.get_recommendations(
            user_id, n * 2, exclude_items
        )
        cf_dict = {item_id: score for item_id, score in cf_recs}
        
        # Get content-based recommendations
        cb_recs = []
        if user_prefs:
            # Use user preferences
            cb_recs = self.cb_model.get_user_recommendations(user_prefs, n * 2)
            
            # Also get recommendations based on liked items
            for liked_item in user_prefs.liked_items[:3]:
                similar = self.cb_model.get_similar_items(
                    liked_item, n // 3, exclude_items
                )
                cb_recs.extend(similar)
        
        cb_dict = {}
        for item_id, score in cb_recs:
            if item_id in cb_dict:
                cb_dict[item_id] = max(cb_dict[item_id], score)
            else:
                cb_dict[item_id] = score
        
        # Combine recommendations
        all_items = set(list(cf_dict.keys()) + list(cb_dict.keys()))
        combined_scores = {}
        
        for item_id in all_items:
            cf_score = cf_dict.get(item_id, 0)
            cb_score = cb_dict.get(item_id, 0)
            
            # Normalize scores
            if cf_dict:
                cf_score = cf_score / max(abs(score) for score in cf_dict.values()) if max(abs(score) for score in cf_dict.values()) > 0 else 0
            if cb_dict:
                cb_score = cb_score / max(cb_dict.values()) if max(cb_dict.values()) > 0 else 0
            
            # Weighted combination
            combined_scores[item_id] = (
                self.cf_weight * cf_score + self.cb_weight * cb_score
            )
        
        # Sort and get top N
        sorted_items = sorted(
            combined_scores.items(), key=lambda x: x[1], reverse=True
        )[:n]
        
        recommendations = []
        for item_id, score in sorted_items:
            metadata = self.items_metadata.get(item_id, {})
            
            # Generate explanation
            explanation = None
            if item_id in cf_dict and item_id in cb_dict:
                explanation = "Recommended based on your ratings and preferences"
            elif item_id in cf_dict:
                explanation = "Recommended based on similar users' ratings"
            elif item_id in cb_dict:
                explanation = "Recommended based on your interests"
            
            recommendations.append(RecommendationItem(
                item_id=item_id,
                title=metadata.get('title', item_id),
                score=round(score, 4),
                explanation=explanation
            ))
        
        return recommendations
    
    def save_models(self, directory: str = "models") -> None:
        """Save trained models."""
        path = Path(directory)
        path.mkdir(exist_ok=True)
        
        with open(path / "cf_model.pkl", 'wb') as f:
            pickle.dump(self.cf_model, f)
        
        with open(path / "cb_model.pkl", 'wb') as f:
            pickle.dump(self.cb_model, f)
        
        with open(path / "metadata.pkl", 'wb') as f:
            pickle.dump(self.items_metadata, f)
        
        logger.info(f"Models saved to {directory}")
    
    @classmethod
    def load_models(cls, directory: str = "models") -> 'HybridRecommender':
        """Load trained models."""
        path = Path(directory)
        
        recommender = cls()
        
        with open(path / "cf_model.pkl", 'rb') as f:
            recommender.cf_model = pickle.load(f)
        
        with open(path / "cb_model.pkl", 'rb') as f:
            recommender.cb_model = pickle.load(f)
        
        with open(path / "metadata.pkl", 'rb') as f:
            recommender.items_metadata = pickle.load(f)
        
        logger.info(f"Models loaded from {directory}")
        return recommender

# Initialize recommender
recommender = HybridRecommender(cf_weight=0.6, cb_weight=0.4)

# Sample data generator for demo
def generate_sample_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate sample data for demonstration."""
    np.random.seed(42)
    
    # Users
    n_users = 100
    user_ids = [f"user_{i}" for i in range(n_users)]
    
    # Items
    n_items = 200
    categories = ['Technology', 'Science', 'Business', 'Health', 'Sports', 'Entertainment']
    item_ids = [f"item_{i}" for i in range(n_items)]
    
    items_data = []
    for i, item_id in enumerate(item_ids):
        category = np.random.choice(categories)
        items_data.append({
            'item_id': item_id,
            'title': f"Product {i}: {category} Item {np.random.randint(1000)}",
            'description': f"Description for {category.lower()} product {i}",
            'category': category,
            'tags': f"{category.lower()}, {'new' if i % 3 == 0 else 'popular'}"
        })
    
    items_df = pd.DataFrame(items_data)
    
    # Ratings
    ratings = []
    for user_id in user_ids:
        n_ratings = np.random.randint(5, 30)
        rated_items = np.random.choice(item_ids, n_ratings, replace=False)
        for item_id in rated_items:
            rating = np.random.randint(1, 6)
            ratings.append({
                'user_id': user_id,
                'item_id': item_id,
                'rating': rating
            })
    
    ratings_df = pd.DataFrame(ratings)
    
    return ratings_df, items_df

@app.on_event("startup")
async def startup_event():
    """Initialize models on startup."""
    global recommender
    
    # Generate and fit sample data
    ratings_df, items_df = generate_sample_data()
    recommender.fit(ratings_df, items_df)
    logger.info("Recommendation system initialized with sample data")

@app.post("/recommendations", response_model=RecommendationResponse)
async def get_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    """
    Get personalized recommendations for a user.
    
    Args:
        request: Recommendation request with user_id and preferences
        
    Returns:
        List of recommended items with scores
    """
    try:
        # Get user preferences (in production, would come from user profile)
        user_prefs = UserPreferences(
            user_id=request.user_id,
            liked_items=[f"item_{i}" for i in np.random.choice(200, 3, replace=False)],
            preferred_categories=np.random.choice(
                ['Technology', 'Science', 'Business'], 2, replace=False
            ).tolist(),
            keywords=['innovation', 'research']
        )
        
        recommendations = recommender.get_recommendations(
            user_id=request.user_id,
            n=request.n_recommendations,
            user_prefs=user_prefs
        )
        
        return RecommendationResponse(
            user_id=request.user_id,
            recommendations=recommendations,
            method="hybrid",
            generated_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Recommendation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error generating recommendations"
        )

@app.post("/similar-items/{item_id}", response_model=RecommendationResponse)
async def get_similar_items(
    item_id: str,
    n: int = Query(default=10, ge=1, le=50)
) -> RecommendationResponse:
    """
    Get similar items to a given item.
    
    Args:
        item_id: Reference item ID
        n: Number of similar items
        
    Returns:
        List of similar items
    """
    try:
        similar = recommender.cb_model.get_similar_items(item_id, n)
        
        recommendations = [
            RecommendationItem(
                item_id=item[0],
                title=recommender.items_metadata.get(item[0], {}).get('title', item[0]),
                score=item[1],
                explanation="Similar content"
            )
            for item in similar
        ]
        
        return RecommendationResponse(
            user_id="anonymous",
            recommendations=recommendations,
            method="content_based",
            generated_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Similar items error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error finding similar items")

@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": recommender.cf_model.is_fitted and recommender.cb_model.is_fitted
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003, reload=True)
