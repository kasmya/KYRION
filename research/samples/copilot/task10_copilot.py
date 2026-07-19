"""
Recommendation System API using FastAPI, scikit-learn, Surprise, and Pandas.
Features:
- Collaborative filtering (SVD)
- Content-based filtering (TF-IDF)
- Hybrid recommendation
- REST API for recommendations
"""

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from surprise import Dataset, Reader, SVD
from surprise.model_selection import train_test_split

app = FastAPI(title="Recommendation System")

# Sample dataset
items = pd.DataFrame({
    "item_id": [1, 2, 3],
    "title": ["Python Basics", "Advanced ML", "Data Science"],
    "description": ["Learn Python", "Deep learning", "Statistics and ML"]
})

ratings = pd.DataFrame({
    "user_id": [1, 1, 2, 2],
    "item_id": [1, 2, 2, 3],
    "rating": [5, 4, 3, 5]
})

# Collaborative filtering model
reader = Reader(rating_scale=(1, 5))
data = Dataset.load_from_df(ratings[["user_id", "item_id", "rating"]], reader)
trainset, _ = train_test_split(data, test_size=0.2)
svd = SVD()
svd.fit(trainset)

# Content-based model
tfidf = TfidfVectorizer(stop_words="english")
tfidf_matrix = tfidf.fit_transform(items["description"])
cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)


class RecommendationRequest(BaseModel):
    user_id: int
    top_n: int = 5


@app.post("/recommend")
def recommend(req: RecommendationRequest) -> List[str]:
    """Hybrid recommendation system."""
    try:
        # Collaborative filtering
        cf_scores = {iid: svd.predict(req.user_id, iid).est for iid in items["item_id"]}
        # Content-based filtering (based on last rated item)
        user_ratings = ratings[ratings["user_id"] == req.user_id]
        if user_ratings.empty:
            cb_scores = {iid: 0 for iid in items["item_id"]}
        else:
            last_item = user_ratings.iloc[-1]["item_id"]
            idx = items[items["item_id"] == last_item].index[0]
            sim_scores = list(enumerate(cosine_sim[idx]))
            cb_scores = {items.iloc[i]["item_id"]: score for i, score in sim_scores}

        # Hybrid score
        hybrid_scores = {iid: cf_scores[iid] + cb_scores.get(iid, 0) for iid in items["item_id"]}
        top_items = sorted(hybrid_scores.items(), key=lambda x: x[1], reverse=True)[:req.top_n]
        return [items[items["item_id"] == iid]["title"].values[0] for iid, _ in top_items]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

