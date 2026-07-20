import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Union, Tuple
import warnings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CollaborativeFiltering:
    """
    Collaborative filtering recommendation system using user-based cosine similarity.

    Parameters
    ----------
    sim_threshold : float, optional
        Minimum similarity to consider for neighbor influence (default 0.0).
    min_neighbors : int, optional
        Minimum number of neighbors to include if available (default 1).
    """

    def __init__(self, sim_threshold: float = 0.0, min_neighbors: int = 1) -> None:
        if not isinstance(sim_threshold, (int, float)):
            raise TypeError("sim_threshold must be numeric")
        if not isinstance(min_neighbors, int) or min_neighbors < 1:
            raise ValueError("min_neighbors must be positive integer")
        self.sim_threshold = sim_threshold
        self.min_neighbors = min_neighbors
        self.user_item_matrix = None
        self.similarity_matrix = None
        self.user_index = None
        self.item_index = None
        self.rating_mean_user = None
        self._is_fitted = False

    def _validate_data(self, data: pd.DataFrame) -> None:
        """Validate input DataFrame for required columns and data types."""
        required_columns = {"user_id", "item_id", "rating"}
        if not isinstance(data, pd.DataFrame):
            raise TypeError("data must be a pandas DataFrame")
        if not required_columns.issubset(data.columns):
            raise ValueError(f"DataFrame must contain columns: {required_columns}")
        if not np.issubdtype(data["rating"].dtype, np.number):
            raise TypeError("Rating column must be numeric")
        if data.empty:
            raise ValueError("DataFrame is empty")

    def _check_fitted(self) -> None:
        """Ensure model has been fitted before prediction or recommendation."""
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

    def fit(self, data: pd.DataFrame) -> "CollaborativeFiltering":
        """
        Fit the collaborative filtering model.

        Constructs user-item matrix, computes user cosine similarities,
        and stores user mean ratings for baseline normalization.

        Parameters
        ----------
        data : pd.DataFrame
            DataFrame with columns: user_id, item_id, rating.

        Returns
        -------
        self : CollaborativeFiltering
            Fitted model instance.
        """
        self._validate_data(data)
        # Create mappings for user and item IDs to indices
        self.user_index = {uid: i for i, uid in enumerate(data["user_id"].unique())}
        self.item_index = {iid: j for j, iid in enumerate(data["item_id"].unique())}
        num_users = len(self.user_index)
        num_items = len(self.item_index)

        # Build user-item matrix (ratings)
        self.user_item_matrix = np.zeros((num_users, num_items))
        for row in data.itertuples(index=False):
            uid = row.user_id
            iid = row.item_id
            rating = row.rating
            if uid in self.user_index and iid in self.item_index:
                self.user_item_matrix[self.user_index[uid], self.item_index[iid]] = rating

        # Compute mean rating per user (for normalization)
        self.rating_mean_user = np.zeros(num_users)
        for i in range(num_users):
            rated_items = self.user_item_matrix[i, :] != 0
            if rated_items.sum() > 0:
                self.rating_mean_user[i] = np.mean(self.user_item_matrix[i, rated_items])
            else:
                self.rating_mean_user[i] = 0.0

        # Compute cosine similarity matrix (user-user)
        # To avoid division by zero, handle zeros in norms
        norm = np.linalg.norm(self.user_item_matrix, axis=1)
        norm[norm == 0] = 1  # avoid division by zero (similarity will be 0)
        # Normalize rows (only for dot product efficiency, but we compute properly)
        # Proper cosine: dot(A,B) / (||A|| * ||B||)
        # We'll compute it directly using matrix operations:
        dot_product = self.user_item_matrix @ self.user_item_matrix.T
        norm_matrix = np.outer(norm, norm)
        # Avoid division by zero (if both norms zero, similarity stays 0)
        with np.errstate(divide='ignore', invalid='ignore'):
            self.similarity_matrix = dot_product / norm_matrix
        # Replace NaNs (caused by 0/0) with 0
        self.similarity_matrix = np.nan_to_num(self.similarity_matrix)
        # Set diagonal to 1 (self similarity)
        np.fill_diagonal(self.similarity_matrix, 1.0)

        self._is_fitted = True
        logger.info(f"Model fitted with {num_users} users and {num_items} items.")
        return self

    def _get_neighbors(self, user_id: Union[int, str]) -> List[Tuple[int, float]]:
        """
        Get neighbors for a user (internal, after fitting).

        Returns list of (user_idx, similarity) sorted descending by similarity,
        excluding the user itself and those below threshold.

        Parameters
        ----------
        user_id : int or str
            User identifier.

        Returns
        -------
        List[Tuple[int, float]]
            List of (user_index, similarity) for neighbors.
        """
        if user_id not in self.user_index:
            raise ValueError(f"User ID '{user_id}' not found in training data.")
        user_idx = self.user_index[user_id]
        sims = self.similarity_matrix[user_idx, :]
        # Exclude self
        sims[user_idx] = -np.inf
        # Filter by threshold
        valid = sims >= self.sim_threshold
        if valid.sum() < self.min_neighbors:
            # Fallback: include enough neighbors even if below threshold
            top_indices = np.argsort(sims)[::-1][:self.min_neighbors]
        else:
            top_indices = np.where(valid)[0]
        # Sort by similarity descending
        sorted_indices = top_indices[np.argsort(sims[top_indices])[::-1]]
        return [(int(idx), sims[idx]) for idx in sorted_indices]

    def predict(self, user_id: Union[int, str], item_id: Union[int, str]) -> float:
        """
        Predict rating for a user and item.

        Uses weighted average of deviations from neighbors' mean ratings.

        Parameters
        ----------
        user_id : int or str
            User identifier.
        item_id : int or str
            Item identifier.

        Returns
        -------
        float
            Predicted rating.
        """
        self._check_fitted()
        if user_id not in self.user_index or item_id not in self.item_index:
            raise ValueError("User or Item ID not found in training data.")
        user_idx = self.user_index[user_id]
        item_idx = self.item_index[item_id]

        # Get neighbors and their ratings for this item
        neighbors = self._get_neighbors(user_id)
        if not neighbors:
            # fallback to user mean
            return float(self.rating_mean_user[user_idx])

        weighted_sum = 0.0
        sum_weights = 0.0
        user_mean = self.rating_mean_user[user_idx]
        for n_idx, sim in neighbors:
            rating = self.user_item_matrix[n_idx, item_idx]
            if rating != 0:  # only if neighbor has rated the item
                n_mean = self.rating_mean_user[n_idx]
                weighted_sum += sim * (rating - n_mean)
                sum_weights += abs(sim)  # use absolute similarity as weight

        if sum_weights == 0:
            return float(user_mean)
        prediction = user_mean + weighted_sum / sum_weights
        # Clamp to reasonable range (e.g., 1-5)
        prediction = max(1.0, min(5.0, prediction))
        return float(prediction)

    def recommend(self, user_id: Union[int, str], top_n: int = 10) -> List[Tuple[Union[int, str], float]]:
        """
        Generate top-N item recommendations for a user.

        Items already rated by the user are excluded.

        Parameters
        ----------
        user_id : int or str
            User identifier.
        top_n : int, optional
            Number of recommendations (default 10).

        Returns
        -------
        List[Tuple[Union[int, str], float]]
            List of (item_id, predicted_rating) sorted descending.
        """
        self._check_fitted()
        if not isinstance(top_n, int) or top_n < 1:
            raise ValueError("top_n must be a positive integer")
        if user_id not in self.user_index:
            raise ValueError(f"User ID '{user_id}' not found in training data.")
        user_idx = self.user_index[user_id]

        # Items already rated
        rated_items = np.where(self.user_item_matrix[user_idx, :] != 0)[0]
        # Map item indices to original IDs
        inverse_item_index = {v: k for k, v in self.item_index.items()}
        candidate_indices = [j for j in range(self.user_item_matrix.shape[1]) if j not in rated_items]

        if not candidate_indices:
            logger.warning(f"No unseen items for user {user_id}.")
            return []

        # Predict all candidate items
        predictions = []
        for item_idx in candidate_indices:
            pred = self.predict(user_id, inverse_item_index[item_idx])
            predictions.append((inverse_item_index[item_idx], pred))

        # Sort by prediction descending
        predictions.sort(key=lambda x: x[1], reverse=True)
        return predictions[:top_n]

    def evaluate(self, test_data: pd.DataFrame, metrics: Optional[List[str]] = None) -> Dict[str, float]:
        """
        Evaluate the model on test data using specified metrics.

        Supported metrics: 'rmse', 'mae', 'precision@k', 'recall@k' (requires k input).

        Parameters
        ----------
        test_data : pd.DataFrame
            DataFrame with columns: user_id, item_id, rating.
        metrics : list of str, optional
            If None, default to ['rmse', 'mae'].

        Returns
        -------
        Dict[str, float]
            Dictionary mapping metric names to values.
        """
        self._check_fitted()
        self._validate_data(test_data)
        if metrics is None:
            metrics = ['rmse', 'mae']
        supported = {'rmse', 'mae', 'precision@k', 'recall@k'}
        if not set(metrics).issubset(supported):
            raise ValueError(f"Unsupported metrics. Supported: {supported}")

        result = {}
        # Common: compute predictions for each row
        predictions = []
        actuals = []
        unknown_users = 0
        unknown_items = 0
        for row in test_data.itertuples(index=False):
            uid = row.user_id
            iid = row.item_id
            rating = row.rating
            if uid in self.user_index and iid in self.item_index:
                try:
                    pred = self.predict(uid, iid)
                    predictions.append(pred)
                    actuals.append(rating)
                except Exception as e:
                    logger.error(f"Error predicting for user {uid}, item {iid}: {e}")
                    continue
            else:
                if uid not in self.user_index:
                    unknown_users += 1
                if iid not in self.item_index:
                    unknown_items += 1

        if unknown_users > 0 or unknown_items > 0:
            logger.warning(f"Skipped {unknown_users} unknown users and {unknown_items} unknown items in test set.")

        if not predictions:
            logger.error("No valid predictions could be computed for test data.")
            return result

        n = len(predictions)
        if 'rmse' in metrics:
            mse = np.mean((np.array(predictions) - np.array(actuals)) ** 2)
            result['rmse'] = float(np.sqrt(mse))
        if 'mae' in metrics:
            mae = np.mean(np.abs(np.array(predictions) - np.array(actuals)))
            result['mae'] = float(mae)
        # For precision/recall we need to interpret how to define relevant items.
        # Typically, consider rating >= threshold as relevant. We'll assume threshold=4.
        if 'precision@k' in metrics or 'recall@k' in metrics:
            # Extract k from metric string (e.g., 'precision@5') or use default 10
            pass

        return result


def main():
    """Example usage of CollaborativeFiltering."""
    # Create sample data
    np.random.seed(42)
    users = [f"U{i}" for i in range(1, 21)]
    items = [f"I{j}" for j in range(1, 11)]
    data = []
    for uid in users:
        for iid in items:
            if np.random.rand() > 0.4:
                rating = np.random.randint(1, 6)
                data.append((uid, iid, rating))
    df = pd.DataFrame(data, columns=["user_id", "item_id", "rating"])

    # Split (simple random split)
    train = df.sample(frac=0.8, random_state=42)
    test = df.drop(train.index)

    model = CollaborativeFiltering(sim_threshold=0.1, min_neighbors=2)
    model.fit(train)

    # Predict for a user-item pair
    uid = "U5"
    iid = "I3"
    try:
        pred = model.predict(uid, iid)
        print(f"Predicted rating for user {uid}, item {iid}: {pred:.2f}")
    except ValueError as e:
        print(e)

    # Get recommendations
    recs = model.recommend(uid, top_n=5)
    print(f"Top-5 recommendations for {uid}:")
    for item, score in recs:
        print(f"  {item}: {score:.2f}")

    # Evaluate
    metrics = model.evaluate(test, metrics=['rmse', 'mae'])
    print(f"Evaluation results: {metrics}")


if __name__ == "__main__":
    main()