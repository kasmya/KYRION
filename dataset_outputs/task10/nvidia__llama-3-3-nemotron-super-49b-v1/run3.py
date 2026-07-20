import numpy as np
import pandas as pd
from scipy import spatial
from typing import Dict, List, Tuple

class CollaborativeFilteringRecommender:
    """
    A collaborative filtering-based recommender system.

    Attributes:
    ----------
    user_item_matrix : pd.DataFrame
        User-item interaction matrix.
    similarity_matrix : np.ndarray
        Precomputed similarity matrix between users.
    """

    def __init__(self, data: pd.DataFrame, user_id_col: str, item_id_col: str, rating_col: str):
        """
        Initialize the recommender system.

        Parameters:
        ----------
        data : pd.DataFrame
            User-item interaction data.
        user_id_col : str
            Column name for user IDs.
        item_id_col : str
            Column name for item IDs.
        rating_col : str
            Column name for ratings.
        """
        self.user_id_col = user_id_col
        self.item_id_col = item_id_col
        self.rating_col = rating_col
        self.user_item_matrix = self._construct_user_item_matrix(data)

    def _construct_user_item_matrix(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Construct the user-item interaction matrix.

        Parameters:
        ----------
        data : pd.DataFrame
            User-item interaction data.

        Returns:
        -------
        pd.DataFrame
            User-item interaction matrix.
        """
        return data.pivot(index=self.user_id_col, columns=self.item_id_col, values=self.rating_col)

    def compute_similarity(self) -> np.ndarray:
        """
        Compute the similarity matrix between users using cosine similarity.

        Returns:
        -------
        np.ndarray
            Similarity matrix between users.
        """
        try:
            self.similarity_matrix = np.zeros((len(self.user_item_matrix), len(self.user_item_matrix)))
            for i in range(len(self.user_item_matrix)):
                for j in range(i, len(self.user_item_matrix)):
                    similarity = 1 - spatial.distance.cosine(self.user_item_matrix.iloc[i], self.user_item_matrix.iloc[j])
                    self.similarity_matrix[i, j] = similarity
                    self.similarity_matrix[j, i] = similarity
            return self.similarity_matrix
        except Exception as e:
            print(f"Error computing similarity: {e}")
            return None

    def get_top_n_recommendations(self, user_id: str, n: int = 10) -> List[Tuple[str, float]]:
        """
        Get the top-N recommendations for a given user.

        Parameters:
        ----------
        user_id : str
            ID of the user.
        n : int, optional
            Number of recommendations. Defaults to 10.

        Returns:
        -------
        List[Tuple[str, float]]
            Top-N recommended items with their predicted ratings.
        """
        try:
            user_index = self.user_item_matrix.index.get_loc(user_id)
            similarities = self.similarity_matrix[user_index]
            similarity_sum = np.sum(similarities)
            if similarity_sum == 0:
                return []
            predicted_ratings = np.dot(similarities, self.user_item_matrix.fillna(0))
            predicted_ratings /= similarity_sum
            predicted_ratings[self.user_item_matrix.loc[user_id] > 0] = -1  # Mask rated items
            top_n_items = np.unravel_index(np.argsort(-predicted_ratings), predicted_ratings.shape)
            return [(item, rating) for item, rating in zip(self.user_item_matrix.columns[top_n_items[1][:n]], predicted_ratings[top_n_items[1][:n]])]
        except Exception as e:
            print(f"Error getting recommendations for {user_id}: {e}")
            return []

    def evaluate(self, test_data: pd.DataFrame, metric: str = "mae") -> float:
        """
        Evaluate the recommender system using the specified metric.

        Parameters:
        ----------
        test_data : pd.DataFrame
            Test data.
        metric : str, optional
            Evaluation metric ("mae" or "rmse"). Defaults to "mae".

        Returns:
        -------
        float
            Evaluation metric value.
        """
        if metric not in ["mae", "rmse"]:
            raise ValueError("Invalid metric. Supported metrics: 'mae', 'rmse'")

        predictions = []
        actuals = []
        for _, row in test_data.iterrows():
            user_id, item_id, rating = row[self.user_id_col], row[self.item_id_col], row[self.rating_col]
            predicted_rating = self.get_top_n_recommendations(user_id, 1)[0][1] if self.get_top_n_recommendations(user_id, 1) else 0
            predictions.append(predicted_rating)
            actuals.append(rating)

        if metric == "mae":
            return np.mean(np.abs(np.array(predictions) - np.array(actuals)))
        elif metric == "rmse":
            return np.sqrt(np.mean((np.array(predictions) - np.array(actuals)) ** 2))


def main():
    # Example usage
    data = pd.DataFrame({
        "user_id": [1, 1, 1, 2, 2, 3, 3, 3, 3],
        "item_id": [101, 102, 103, 101, 103, 101, 102, 103, 104],
        "rating": [4, 3, 5, 2, 4, 5, 3, 4, 5]
    })

    recommender = CollaborativeFilteringRecommender(data, "user_id", "item_id", "rating")
    recommender.compute_similarity()

    user_id = 1
    top_n_recommendations = recommender.get_top_n_recommendations(user_id)
    print(f"Top recommendations for user {user_id}: {top_n_recommendations}")

    test_data = pd.DataFrame({
        "user_id": [1, 2, 3],
        "item_id": [104, 102, 101],
        "rating": [4, 3, 5]
    })
    evaluation_metric = recommender.evaluate(test_data, metric="mae")
    print(f"Evaluation metric (MAE): {evaluation_metric}")


if __name__ == "__main__":
    main()