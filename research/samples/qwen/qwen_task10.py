"""FastAPI Recommendation System with Collaborative and Content-Based Filtering."""
import logging
from typing import List, Dict
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.sparse.linalg import svds

logging.basicConfig(level=logging.INFO)
app = FastAPI()

# Mock Data
users = [1, 2, 3, 4, 5]
items = [101, 102, 103, 104, 105]
ratings_data = {
    'user_id': [1, 1, 2, 2, 3, 3, 4, 5, 5],
    'item_id': [101, 102, 101, 103, 102, 104, 105, 103, 105],
    'rating': [5, 3, 4, 2, 5, 4, 3, 4, 5]
}
item_descriptions = {
    101: "sci-fi space adventure",
    102: "romantic comedy drama",
    103: "action thriller movie",
    104: "historical documentary",
    105: "sci-fi cyberpunk"
}

df = pd.DataFrame(ratings_data)
user_item_matrix = df.pivot_table(index='user_id', columns='item_id', values='rating').fillna(0)

# Content-based setup
tfidf = TfidfVectorizer(stop_words='english')
desc_df = pd.DataFrame(list(item_descriptions.items()), columns=['item_id', 'description'])
tfidf_matrix = tfidf.fit_transform(desc_df['description'])

class RecRequest(BaseModel):
    user_id: int
    top_n: int = 3

def collaborative_filter(user_id: int, top_n: int) -> List[int]:
    """SVD-based collaborative filtering."""
    if user_id not in user_item_matrix.index:
        return []
    matrix = user_item_matrix.values
    u, sigma, vt = svds(matrix.astype(float), k=min(matrix.shape)-1)
    sigma = np.diag(sigma)
    all_pred = np.dot(np.dot(u, sigma), vt)
    pred_df = pd.DataFrame(all_pred, columns=user_item_matrix.columns, index=user_item_matrix.index)
    
    user_preds = pred_df.loc[user_id].sort_values(ascending=False)
    # Filter out already rated items
    rated = user_item_matrix.loc[user_id][user_item_matrix.loc[user_id] > 0].index.tolist()
    return user_preds.drop(rated).head(top_n).index.tolist()

def content_based(item_ids: List[int], top_n: int) -> List[int]:
    """TF-IDF based content filtering."""
    if not item_ids: return []
    idx = desc_df[desc_df['item_id'].isin(item_ids)].index
    if idx.empty: return []
    sim_scores = cosine_similarity(tfidf_matrix[idx], tfidf_matrix).mean(axis=0)
    top_indices = np.argsort(sim_scores)[::-1][:top_n + len(item_ids)]
    recs = [desc_df.iloc[i]['item_id'] for i in top_indices if desc_df.iloc[i]['item_id'] not in item_ids]
    return recs[:top_n]

@app.post("/recommend")
def get_recommendations(req: RecRequest):
    try:
        cf_recs = collaborative_filter(req.user_id, req.top_n)
        # Hybrid: blend CF with CB based on CF results
        cb_recs = content_based(cf_recs[:2], req.top_n) if cf_recs else []
        final_recs = list(dict.fromkeys(cf_recs + cb_recs))[:req.top_n]
        return {"user_id": req.user_id, "recommendations": final_recs}
    except Exception as e:
        logging.error(f"Rec error: {e}")
        raise HTTPException(500, "Recommendation failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)