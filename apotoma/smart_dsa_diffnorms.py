import os
from typing import List, Optional

import numpy as np
import tensorflow as tf

from apotoma.surprise_adequacy import DSA, SurpriseAdequacyConfig


class DiffOfNormsSelectiveDSA(DSA):

    def __init__(self,
                 model: tf.keras.Model,
                 train_data: np.ndarray,
                 config: SurpriseAdequacyConfig,
                 threshold=1e-3,
                 dsa_batch_size: int = 500,
                 max_workers: Optional[int] = None) -> None:
        super().__init__(model, train_data, config, dsa_batch_size, max_workers)
        self.threshold = threshold

    def _load_or_calc_train_ats(self, use_cache=False) -> None:

        saved_train_path = self._get_saved_path("train")

        if os.path.exists(saved_train_path[0]) and use_cache:
            print("Found saved {} ATs, skip serving".format("train"))
            # In case train_ats is stored in a disk
            self.train_ats, self.train_pred = np.load(saved_train_path[0]), np.load(saved_train_path[1])

        else:
            self.train_ats, self.train_pred = self._load_or_calculate_ats(dataset=self.train_data, ds_type="train",
                                                                          use_cache=use_cache)
        self._select_smart_ats()

    def prep(self, use_cache: bool = False) -> None:
        self._load_or_calc_train_ats(use_cache=use_cache)

    def _select_smart_ats(self):

        all_train_ats = self.train_ats
        all_train_pred = self.train_pred

        new_class_matrix_norms_vec = {}
        for label in range(self.config.num_classes):

            available_indices = np.where(all_train_pred == label)
            data_label = all_train_ats[available_indices]
            norms = np.linalg.norm(data_label, axis=1)  # Norms

            indexes = np.arange(norms.shape[0])
            is_available = np.ones(shape=norms.shape[0], dtype=bool)

            # This index used in the loop indicates the latest element selected to be added to chosen items
            current_idx = 0

            while True:
                # Get all indexes (higher than current_index) which are still available and the corresponding ats
                candidate_indexes = np.argwhere((indexes > current_idx) & is_available).flatten()
                candidates = norms[candidate_indexes]

                # Calculate the diff between norms
                diffs = np.abs(candidates - norms[current_idx])

                # Identify candidates which are too similar to currently added element (current_idx)
                # and set their availability to false
                remove_candidate_indexes = np.flatnonzero(diffs < self.threshold)
                remove_overall_indexes = candidate_indexes[remove_candidate_indexes]
                is_available[remove_overall_indexes] = False

                # Select the next available candidate as current_idx (i.e., use select it for use in dsa),
                #   or break if none available
                if np.count_nonzero(is_available[current_idx:]) > 1:
                    current_idx = np.argmax(is_available[current_idx + 1:]) + (current_idx + 1)
                else:
                    break

            selected_indexes = np.nonzero(is_available)[0]
            new_class_matrix_norms_vec[label] = list(available_indices[0][selected_indexes])

        self.class_matrix = new_class_matrix_norms_vec
        self.number_of_samples = sum(len(lst) for lst in new_class_matrix_norms_vec.values())

    def sample_diff_distributions(self, x_subarray: np.ndarray) -> np.ndarray:
        """
        Calculates all differences between the samples passed in the subarray.
        This can be used to guess thresholds for the algorithm.
        The threshold passed when creating this DSA instance is ignored.
        :param x_subarray: the subset of the train data (or any other data) for which to calc the differences
        :return: Sorted one-dimensional array of differences
        """
        ats, pred = self._calculate_ats(x_subarray)
        norms = np.linalg.norm(ats, axis=1)  # Norms
        unique_pred = np.unique(pred)
        differences = []
        for label in unique_pred:
            label_indices = np.where(pred == label)
            values = norms[label_indices]
            assert values.ndim == 1
            diff_matrix = np.abs(values - np.expand_dims(values, 1))
            indeces_under_diagonal = np.tril_indices(diff_matrix.shape[0], -1)
            diffs = diff_matrix[indeces_under_diagonal]
            differences += list(diffs)
        return np.array(sorted(differences))


