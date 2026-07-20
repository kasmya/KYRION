import numpy as np
import pandas as pd
from scipy import spatial
from typing import Dict, List, Tuple

class CollaborativeFiltering:
    """
    A class implementing a collaborative filtering recommendation system.

    Attributes:
    ----------
    user_item_matrix : np.ndarray
        A 2D numpy array representing the user-item interaction matrix.
    num_users : int
        The number of users in the system.
    num_items : int
        The number of items in the system.

    Methods:
    -------
    compute_similarity(user_id: int) -> Dict[int, float]
        Compute the cosine similarity between the given user and all other users.
    get_top_n_recommendations(user_id: int, n: int) -> List[int]
        Return the top-N recommended items for the given user.
    evaluate(recommendations: List[int], actual_ratings: List[float]) -> Tuple[float, float]
        Evaluate the recommendation system using precision and recall metrics.
    """

    def __init__(self, user_item_matrix: np.ndarray):
        """
        Initialize the collaborative filtering system with a user-item matrix.

        Args:
        ----
        user_item_matrix (np.ndarray): A 2D numpy array representing the user-item interaction matrix.
        """
        self.user_item_matrix = user_item_matrix
        self.num_users, self.num_items = user_item_matrix.shape

    def compute_similarity(self, user_id: int) -> Dict[int, float]:
        """
        Compute the cosine similarity between the given user and all other users.

        Args:
        ----
        user_id (int): The ID of the user for whom to compute similarities.

        Returns:
        -------
        Dict[int, float]: A dictionary mapping user IDs to their corresponding cosine similarities.
        """
        user_vector = self.user_item_matrix[user_id]
        similarities = {}
        for i in range(self.num_users):
            if i != user_id:
                similarity = 1 - spatial.distance.cosine(user_vector, self.user_item_matrix[i])
                similarities[i] = similarity
        return similarities

    def get_top_n_recommendations(self, user_id: int, n: int) -> List[int]:
        """
        Return the top-N recommended items for the given user.

        Args:
        ----
        user_id (int): The ID of the user for whom to generate recommendations.
        n (int): The number of recommendations to generate.

        Returns:
        -------
        List[int]: A list of the top-N recommended item IDs.
        """
        similarities = self.compute_similarity(user_id)
        sorted_similarities = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        recommended_items = []
        for similar_user_id, _ in sorted_similarities:
            similar_user_vector = self.user_item_matrix[similar_user_id]
            for item_id in range(self.num_items):
                if self.user_item_matrix[user_id, item_id] == 0 and similar_user_vector[item_id] != 0:
                    recommended_items.append(item_id)
                    if len(recommended_items) == n:
                        break
            if len(recommended_items) == n:
                break
        return recommended_items

    def evaluate(self, recommendations: List[int], actual_ratings: List[float]) -> Tuple[float, float]:
        """
        Evaluate the recommendation system using precision and recall metrics.

        Args:
        ----
        recommendations (List[int]): A list of recommended item IDs.
        actual_ratings (List[float]): A list of actual ratings for the recommended items.

        Returns:
        -------
        Tuple[float, float]: A tuple containing the precision and recall of the recommendation system.
        """
        relevant_items = [item_id for item_id, rating in zip(recommendations, actual_ratings) if rating > 0]
        precision = len(relevant_items) / len(recommendations) if recommendations else 0
        recall = len(relevant_items) / len([rating for rating in actual_ratings if rating > 0]) if actual_ratings else 0
        return precision, recall


def main():
    # Example usage
    user_item_matrix = np.array([
        [5, 3, 0, 1],
        [4, 0, 0, 1],
        [1, 1, 0, 5],
        [1, 0, 0, 4],
        [0, 1, 5, 4]
    ])

    cf = CollaborativeFiltering(user_item_matrix)
    user_id = 0
    n = 3
    recommendations = cf.get_top_n_recommendations(user_id, n)
    print(f"Recommended items for user {user_id}: {recommendations}")

    actual_ratings = [0, 0, 0, 0]  # Replace with actual ratings
    precision, recall = cf.evaluate(recommendations, actual_ratings)
    print(f"Precision: {precision:.2f}, Recall: {recall:.2f}")


if __name__ == "__main__":
    main()