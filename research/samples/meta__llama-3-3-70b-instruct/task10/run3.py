import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

class CollaborativeFiltering:
    """
    A class for building a collaborative filtering-based recommendation system.

    Attributes:
    - user_item_matrix (np.ndarray): A 2D matrix where rows represent users and columns represent items.
    - similarity_matrix (np.ndarray): A 2D matrix where each entry represents the similarity between two users.
    """

    def __init__(self, user_item_data: Dict[int, Dict[int, int]]):
        """
        Initializes the CollaborativeFiltering class.

        Args:
        - user_item_data (Dict[int, Dict[int, int]]): A dictionary where keys are user IDs and values are dictionaries.
            The inner dictionaries have item IDs as keys and ratings as values.

        Raises:
        - ValueError: If the input data is empty or not in the correct format.
        """
        if not user_item_data:
            raise ValueError("Input data is empty")

        self.user_item_matrix = self._construct_user_item_matrix(user_item_data)
        self.similarity_matrix = self._compute_similarity_matrix(self.user_item_matrix)

    def _construct_user_item_matrix(self, user_item_data: Dict[int, Dict[int, int]]) -> np.ndarray:
        """
        Constructs the user-item matrix from the input data.

        Args:
        - user_item_data (Dict[int, Dict[int, int]]): A dictionary where keys are user IDs and values are dictionaries.
            The inner dictionaries have item IDs as keys and ratings as values.

        Returns:
        - np.ndarray: A 2D matrix where rows represent users and columns represent items.
        """
        # Get all unique user and item IDs
        user_ids = list(user_item_data.keys())
        item_ids = set()
        for user in user_item_data.values():
            item_ids.update(user.keys())
        item_ids = list(item_ids)

        # Create the user-item matrix
        matrix = np.zeros((len(user_ids), len(item_ids)))
        for i, user in enumerate(user_ids):
            for j, item in enumerate(item_ids):
                if item in user_item_data[user]:
                    matrix[i, j] = user_item_data[user][item]

        return matrix

    def _compute_similarity_matrix(self, user_item_matrix: np.ndarray) -> np.ndarray:
        """
        Computes the similarity matrix using cosine similarity.

        Args:
        - user_item_matrix (np.ndarray): A 2D matrix where rows represent users and columns represent items.

        Returns:
        - np.ndarray: A 2D matrix where each entry represents the similarity between two users.
        """
        # Compute cosine similarity between all pairs of users
        similarity_matrix = np.dot(user_item_matrix, user_item_matrix.T)
        norms = np.linalg.norm(user_item_matrix, axis=1)[:, np.newaxis]
        similarity_matrix /= np.dot(norms, norms.T)

        return similarity_matrix

    def get_top_n_recommendations(self, user_id: int, n: int) -> List[Tuple[int, float]]:
        """
        Gets the top-N recommendations for a given user.

        Args:
        - user_id (int): The ID of the user for whom to get recommendations.
        - n (int): The number of recommendations to return.

        Returns:
        - List[Tuple[int, float]]: A list of tuples, where each tuple contains an item ID and its predicted rating.
        """
        # Get the similarity scores for the given user
        similarity_scores = self.similarity_matrix[user_id]

        # Get the items that the given user has not rated
        unrated_items = np.where(self.user_item_matrix[user_id] == 0)[0]

        # Get the predicted ratings for the unrated items
        predicted_ratings = []
        for item in unrated_items:
            # Compute the predicted rating using the similarity scores
            predicted_rating = np.dot(similarity_scores, self.user_item_matrix[:, item]) / np.sum(similarity_scores)
            predicted_ratings.append((item, predicted_rating))

        # Return the top-N recommended items
        return sorted(predicted_ratings, key=lambda x: x[1], reverse=True)[:n]

    def evaluate(self, test_data: Dict[int, Dict[int, int]]) -> Dict[str, float]:
        """
        Evaluates the performance of the recommendation system using the test data.

        Args:
        - test_data (Dict[int, Dict[int, int]]): A dictionary where keys are user IDs and values are dictionaries.
            The inner dictionaries have item IDs as keys and ratings as values.

        Returns:
        - Dict[str, float]: A dictionary containing the evaluation metrics (e.g., precision, recall, F1 score).
        """
        # Compute the evaluation metrics
        precision = 0
        recall = 0
        f1_score = 0
        for user, items in test_data.items():
            recommended_items = self.get_top_n_recommendations(user, len(items))
            recommended_item_ids = [item[0] for item in recommended_items]
            actual_item_ids = list(items.keys())
            precision += len(set(recommended_item_ids) & set(actual_item_ids)) / len(recommended_item_ids)
            recall += len(set(recommended_item_ids) & set(actual_item_ids)) / len(actual_item_ids)
            f1_score += 2 * len(set(recommended_item_ids) & set(actual_item_ids)) / (len(recommended_item_ids) + len(actual_item_ids))

        # Return the evaluation metrics
        return {
            "precision": precision / len(test_data),
            "recall": recall / len(test_data),
            "f1_score": f1_score / len(test_data)
        }

# Example usage
if __name__ == "__main__":
    user_item_data = {
        0: {0: 5, 1: 3, 2: 0, 3: 1, 4: 4},
        1: {0: 4, 1: 0, 2: 0, 3: 1, 4: 1},
        2: {0: 1, 1: 1, 2: 5, 3: 4, 4: 0},
        3: {0: 1, 1: 0, 2: 0, 3: 0, 4: 0},
        4: {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    }
    test_data = {
        0: {0: 5, 1: 3, 2: 0, 3: 1, 4: 4},
        1: {0: 4, 1: 0, 2: 0, 3: 1, 4: 1},
        2: {0: 1, 1: 1, 2: 5, 3: 4, 4: 0},
        3: {0: 1, 1: 0, 2: 0, 3: 0, 4: 0},
        4: {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    }

    cf = CollaborativeFiltering(user_item_data)
    recommendations = cf.get_top_n_recommendations(0, 3)
    print("Recommended items:", recommendations)

    evaluation_metrics = cf.evaluate(test_data)
    print("Evaluation metrics:", evaluation_metrics)