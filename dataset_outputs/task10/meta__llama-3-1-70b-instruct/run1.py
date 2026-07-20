import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy import spatial

class RecommendationSystem:
    """
    A collaborative filtering-based recommendation system.

    Attributes:
    ----------
    user_item_matrix : pd.DataFrame
        A matrix where rows represent users and columns represent items.
    similarity_matrix : pd.DataFrame
        A matrix where rows and columns represent users and the cell at (i, j)
        represents the similarity between users i and j.

    Methods:
    -------
    construct_user_item_matrix(user_item_data: Dict[str, List[int]]) -> None
        Construct the user-item matrix from user-item interaction data.
    compute_similarity() -> None
        Compute the similarity between each pair of users using cosine similarity.
    get_top_n_recommendations(user_id: str, n: int) -> List[Tuple[int, float]]
        Get the top-N recommended items for a given user.
    evaluate(system_user_item_matrix: pd.DataFrame, test_user_item_matrix: pd.DataFrame) -> Dict[str, float]
        Evaluate the recommendation system using precision, recall, and F1-score.
    """

    def __init__(self):
        """
        Initialize the recommendation system.
        """
        self.user_item_matrix = None
        self.similarity_matrix = None

    def construct_user_item_matrix(self, user_item_data: Dict[str, List[int]]) -> None:
        """
        Construct the user-item matrix from user-item interaction data.

        Parameters:
        ----------
        user_item_data : Dict[str, List[int]]
            A dictionary where keys are user IDs and values are lists of item IDs
            that the user has interacted with.
        """
        users = list(user_item_data.keys())
        items = set()
        for user in users:
            items.update(user_item_data[user])
        items = list(items)
        self.user_item_matrix = pd.DataFrame(index=users, columns=items)
        for user in users:
            for item in user_item_data[user]:
                self.user_item_matrix.loc[user, item] = 1
        self.user_item_matrix.fillna(0, inplace=True)

    def compute_similarity(self) -> None:
        """
        Compute the similarity between each pair of users using cosine similarity.
        """
        if self.user_item_matrix is None:
            raise ValueError("User-item matrix is not constructed.")
        self.similarity_matrix = pd.DataFrame(index=self.user_item_matrix.index, columns=self.user_item_matrix.index)
        for user1 in self.user_item_matrix.index:
            for user2 in self.user_item_matrix.index:
                if user1 == user2:
                    continue
                similarity = 1 - spatial.distance.cosine(self.user_item_matrix.loc[user1], self.user_item_matrix.loc[user2])
                self.similarity_matrix.loc[user1, user2] = similarity

    def get_top_n_recommendations(self, user_id: str, n: int) -> List[Tuple[int, float]]:
        """
        Get the top-N recommended items for a given user.

        Parameters:
        ----------
        user_id : str
            The ID of the user for whom to generate recommendations.
        n : int
            The number of recommendations to generate.

        Returns:
        -------
        List[Tuple[int, float]]
            A list of tuples, where each tuple contains an item ID and a predicted rating.
        """
        if self.similarity_matrix is None:
            raise ValueError("Similarity matrix is not computed.")
        if user_id not in self.user_item_matrix.index:
            raise ValueError("User ID is not in the user-item matrix.")
        similarity_scores = self.similarity_matrix.loc[user_id]
        similarity_scores = similarity_scores[similarity_scores > 0]
        recommended_items = []
        for item in self.user_item_matrix.columns:
            if self.user_item_matrix.loc[user_id, item] == 1:
                continue
            predicted_rating = 0
            for neighbor_user in similarity_scores.index:
                predicted_rating += similarity_scores[neighbor_user] * self.user_item_matrix.loc[neighbor_user, item]
            recommended_items.append((item, predicted_rating))
        recommended_items.sort(key=lambda x: x[1], reverse=True)
        return recommended_items[:n]

    def evaluate(self, system_user_item_matrix: pd.DataFrame, test_user_item_matrix: pd.DataFrame) -> Dict[str, float]:
        """
        Evaluate the recommendation system using precision, recall, and F1-score.

        Parameters:
        ----------
        system_user_item_matrix : pd.DataFrame
            The user-item matrix used by the recommendation system.
        test_user_item_matrix : pd.DataFrame
            The test user-item matrix used for evaluation.

        Returns:
        -------
        Dict[str, float]
            A dictionary containing precision, recall, and F1-score.
        """
        precision = 0
        recall = 0
        f1_score = 0
        for user in system_user_item_matrix.index:
            recommended_items = self.get_top_n_recommendations(user, 10)
            recommended_items = [item[0] for item in recommended_items]
            actual_items = test_user_item_matrix.loc[user].loc[test_user_item_matrix.loc[user] == 1].index.tolist()
            precision += len(set(recommended_items) & set(actual_items)) / len(recommended_items)
            recall += len(set(recommended_items) & set(actual_items)) / len(actual_items)
            f1_score += 2 * precision * recall / (precision + recall)
        precision /= len(system_user_item_matrix.index)
        recall /= len(system_user_item_matrix.index)
        f1_score /= len(system_user_item_matrix.index)
        return {"precision": precision, "recall": recall, "f1_score": f1_score}

# Example usage:
if __name__ == "__main__":
    user_item_data = {
        "user1": [1, 2, 3],
        "user2": [2, 3, 4],
        "user3": [1, 3, 5]
    }
    rs = RecommendationSystem()
    rs.construct_user_item_matrix(user_item_data)
    rs.compute_similarity()
    recommended_items = rs.get_top_n_recommendations("user1", 3)
    print(recommended_items)
    system_user_item_matrix = rs.user_item_matrix
    test_user_item_matrix = pd.DataFrame(index=["user1", "user2", "user3"], columns=[1, 2, 3, 4, 5])
    test_user_item_matrix.loc["user1", 1] = 1
    test_user_item_matrix.loc["user1", 2] = 1
    test_user_item_matrix.loc["user2", 2] = 1
    test_user_item_matrix.loc["user2", 3] = 1
    test_user_item_matrix.loc["user3", 1] = 1
    test_user_item_matrix.loc["user3", 3] = 1
    evaluation_metrics = rs.evaluate(system_user_item_matrix, test_user_item_matrix)
    print(evaluation_metrics)