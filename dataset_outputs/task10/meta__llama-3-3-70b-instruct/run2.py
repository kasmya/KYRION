import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy import spatial

class CollaborativeFiltering:
    """
    A class used to implement a recommendation system using collaborative filtering.

    Attributes:
    ----------
    user_item_matrix : pd.DataFrame
        A matrix where the rows represent users and the columns represent items.
    num_recommendations : int
        The number of recommendations to return for a given user.
    """

    def __init__(self, user_item_matrix: pd.DataFrame, num_recommendations: int = 10):
        """
        Parameters:
        ----------
        user_item_matrix : pd.DataFrame
            A matrix where the rows represent users and the columns represent items.
        num_recommendations : int
            The number of recommendations to return for a given user (default is 10).
        """
        self.user_item_matrix = user_item_matrix
        self.num_recommendations = num_recommendations

    def compute_similarity(self, user1: int, user2: int) -> float:
        """
        Compute the cosine similarity between two users.

        Parameters:
        ----------
        user1 : int
            The index of the first user.
        user2 : int
            The index of the second user.

        Returns:
        -------
        float
            The cosine similarity between the two users.
        """
        user1_vector = self.user_item_matrix.iloc[user1].values
        user2_vector = self.user_item_matrix.iloc[user2].values
        return 1 - spatial.distance.cosine(user1_vector, user2_vector)

    def get_recommendations(self, user: int) -> List[Tuple[int, float]]:
        """
        Get the top-N recommendations for a given user.

        Parameters:
        ----------
        user : int
            The index of the user.

        Returns:
        -------
        List[Tuple[int, float]]
            A list of tuples containing the item index and the predicted rating.
        """
        # Compute similarity with all other users
        similarities = []
        for other_user in range(len(self.user_item_matrix)):
            if other_user != user:
                similarity = self.compute_similarity(user, other_user)
                similarities.append((other_user, similarity))

        # Sort users by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Get top-N similar users
        top_similar_users = similarities[:self.num_recommendations]

        # Get items rated by top-N similar users
        recommended_items = []
        for similar_user, _ in top_similar_users:
            similar_user_vector = self.user_item_matrix.iloc[similar_user].values
            for item, rating in enumerate(similar_user_vector):
                if rating > 0 and self.user_item_matrix.iloc[user, item] == 0:
                    recommended_items.append((item, rating))

        # Sort recommended items by rating
        recommended_items.sort(key=lambda x: x[1], reverse=True)

        return recommended_items[:self.num_recommendations]

    def evaluate(self, test_user_item_matrix: pd.DataFrame) -> Dict[str, float]:
        """
        Evaluate the recommendation system using the test user-item matrix.

        Parameters:
        ----------
        test_user_item_matrix : pd.DataFrame
            The test user-item matrix.

        Returns:
        -------
        Dict[str, float]
            A dictionary containing the evaluation metrics (precision, recall, F1 score).
        """
        precision = 0
        recall = 0
        f1_score = 0
        for user in range(len(test_user_item_matrix)):
            recommended_items = self.get_recommendations(user)
            recommended_items = [item for item, _ in recommended_items]
            actual_items = test_user_item_matrix.iloc[user].nonzero()[0]
            precision += len(set(recommended_items) & set(actual_items)) / len(recommended_items)
            recall += len(set(recommended_items) & set(actual_items)) / len(actual_items)
            f1_score += 2 * len(set(recommended_items) & set(actual_items)) / (len(recommended_items) + len(actual_items))
        precision /= len(test_user_item_matrix)
        recall /= len(test_user_item_matrix)
        f1_score /= len(test_user_item_matrix)
        return {"precision": precision, "recall": recall, "f1_score": f1_score}

def main():
    try:
        # Example usage
        user_item_matrix = pd.DataFrame([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [1, 1, 0, 0],
            [0, 0, 1, 1]
        ])
        test_user_item_matrix = pd.DataFrame([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        cf = CollaborativeFiltering(user_item_matrix)
        recommendations = cf.get_recommendations(0)
        print("Recommendations for user 0:")
        for item, rating in recommendations:
            print(f"Item {item}: {rating}")
        evaluation_metrics = cf.evaluate(test_user_item_matrix)
        print("Evaluation metrics:")
        for metric, value in evaluation_metrics.items():
            print(f"{metric.capitalize()}: {value:.4f}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()