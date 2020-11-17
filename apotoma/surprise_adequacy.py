from typing import Tuple, Dict, List

import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Model
from apotoma.novelty_score import NoveltyScore
from scipy.stats import gaussian_kde
from tqdm import tqdm


class SurpriseAdequacy(NoveltyScore):

    def __init__(self, model: tf.keras.Model, train_data: tf.data.Dataset, test_data:tf.data.Dataset, args: {}) -> None:
        super().__init__(model, train_data, test_data, args)
        self.train_ats, self.train_pred, self.class_matrix = None, None, {}

    # Returns ats and returns predictions
    def _calculate_ats(self, dataset: tf.data.Dataset, ds_name: str) -> Tuple[np.ndarray, np.ndarray]:
        print(f"Assume we calculated the ats for {ds_name} dataset")


        temp_model = Model(
            inputs=self.model.input,
            outputs=[self.model.get_layer(layer_name).output for layer_name in self.args.layer_names],
        )

        if self.args.is_classification:
            #p = Pool(num_proc)
            print("["+ds_name+"]"+" Model serving")
            # Shape of 60000, predictions for the training set
            pred = self.model.predict_classes(dataset, batch_size=self.args.batch_size, verbose=1)
            if len(self.args.layer_names) == 1:
                # layer_outputs is 60,000 * 10, since there are 10 nodes in activation_3
                layer_outputs = [
                    temp_model.predict(dataset, batch_size=self.args.batch_size, verbose=1)
                ]

            else:
                layer_outputs = temp_model.predict(
                    dataset, batch_size=self.args.batch_size, verbose=1
                )

            print("Processing "+ds_name+" ATs")
            ats = None
            for layer_name, layer_output in zip(self.args.layer_names, layer_outputs):
                print("Layer: " + layer_name)
                if layer_output[0].ndim == 3:
                    # For convolutional layers
                    layer_matrix = np.array(
                        map(lambda x: [np.mean(x[..., j]) for j in range(x.shape[-1])], [layer_output[i] for i in range(len(dataset))])
                    )
                else:
                    layer_matrix = np.array(layer_output)

                if ats is None:
                    # Initially ats is None, so ats is 60,000 * 10
                    ats = layer_matrix
                else:
                    ats = np.append(ats, layer_matrix, axis=1)
                    layer_matrix = None

        """ 
                    if save_path is not None:
                    np.save(save_path[0], ats)
                    np.save(save_path[1], pred)
                    print("Assume we cache the train ats and predictions here")
        """
        return ats, pred


    # TODO: Think about (long term): Maybe no caching as we keep this in memory anyways
    def _get_or_calc_train_ats(self):
        is_cached = False  # TODO Replace with call to see if cached arrays exist
        if is_cached:
            return None, None  # TODO return loaded arrays
        else:
            self.train_ats, self.train_pred = self._calculate_ats(dataset=self.train_data, ds_name="train")
            # TODO cache to FS

    def prep(self):
        self.train_ats, self.train_pred = self._get_or_calc_train_ats()
        for i, label in enumerate(self.train_pred):
            if label not in self.class_matrix:
                self.class_matrix[label] = []
            self.class_matrix[label].append(i)


class LSA(SurpriseAdequacy):

    def calc(self, target_data: tf.data.Dataset, ds_name: str):
        target_ats, target_pred = self._calculate_ats(dataset=target_data, ds_name=ds_name)

        kdes, removed_rows = self._calc_kdes()
        return self._calc_lsa(target_ats, target_pred, kdes, removed_rows, ds_name)

    def _calc_kdes(self) -> Tuple[List[object], List[int]]:  # Replace None with kde scipy object type

        removed_rows = []
        if self.args.is_classification:

            for label in range(self.args.num_classes):
                # Shape of (num_activation nodes x num_examples_by_label)
                row_vectors = np.transpose(self.train_ats[self.class_matrix[label]])
                for i in range(row_vectors.shape[0]):
                    if (
                            np.var(row_vectors[i]) < self.args.var_threshold
                            and i not in removed_rows
                    ):
                        # Add activation node to removed_rows
                        removed_rows.append(i)

            kdes = {}
            for label in tqdm(range(self.args.num_classes), desc="kde"):

                refined_ats = np.transpose(self.train_ats[self.class_matrix[label]])
                refined_ats = np.delete(refined_ats, removed_rows, axis=0)

                if refined_ats.shape[0] == 0:
                    print(
                        "Ats were removed by threshold {}".format(self.args.var_threshold)
                    )
                    break
                kdes[label] = gaussian_kde(refined_ats)

        else:
            row_vectors = np.transpose(self.train_ats)
            for activation_node in range(row_vectors.shape[0]):
                if np.var(row_vectors[activation_node]) < self.args.var_threshold:
                    removed_rows.append(activation_node)

            refined_ats = np.transpose(self.train_ats)
            refined_ats = np.delete(refined_ats, removed_rows, axis=0)
            if refined_ats.shape[0] == 0:
                print("Ats were removed by threshold {}".format(self.args.var_threshold))
            kdes = [gaussian_kde(refined_ats)]

        print("The number of removed columns: {}".format(len(removed_rows)))

        return kdes, removed_rows

    def _calc_lsa(self, target_ats, target_pred, kdes, removed_rows, ds_name):

        lsa = []
        print("[" + ds_name + "] " + "Fetching LSA")

        if self.args.is_classification:
            for i, at in enumerate(tqdm(target_ats)):
                label = target_pred[i]
                kde = kdes[label]
                refined_at = np.delete(at, removed_rows, axis=0)
                lsa.append(np.asscalar(-kde.logpdf(np.transpose(refined_at))))
        else:
            kde = kdes[0]
            for at in tqdm(target_ats):
                refined_at = np.delete(at, removed_rows, axis=0)
                lsa.append(np.asscalar(-kde.logpdf(np.transpose(refined_at))))

        return lsa

class DSA(SurpriseAdequacy):

    def calc(self, target_data: tf.data.Dataset, ds_name: str):
        target_ats, target_pred = self._calculate_ats(dataset=target_data, ds_name=ds_name)
        return self._calc_dsa(target_ats, target_pred, ds_name)

    def _calc_dsa(self, target_ats, target_pred, ds_name):

        dsa = np.empty(shape=target_pred.shape[0])
        batch_size = 500
        start = 0
        all_idx = list(range(len(self.train_pred)))

        print("[" + ds_name + "] " + "Fetching DSA")

        while start < target_pred.shape[0]:
            batch = target_pred[start:start + batch_size]
            for label in range(self.args.num_classes):

                matches = np.where(batch == label)
                if len(matches) > 0:
                    target_matches = target_ats[matches[0] + start]
                    train_matches_sameClass = self.train_ats[self.class_matrix[label]]
                    a_dist = target_matches[:, None] - train_matches_sameClass
                    a_dist_norms = np.linalg.norm(a_dist, axis=2)
                    a_min_dist = np.min(a_dist_norms, axis=1)
                    closest_position = np.argmin(a_dist_norms, axis=1)
                    closest_ats = train_matches_sameClass[closest_position]

                    train_matches_otherClasses = self.train_ats[list(set(all_idx) - set(self.class_matrix[label]))]
                    b_dist = closest_ats[:, None] - train_matches_otherClasses
                    b_dist_norms = np.linalg.norm(b_dist, axis=2)
                    b_min_dist = np.min(b_dist_norms, axis=1)

                    dsa[matches[0] + start] = a_min_dist / b_min_dist

                else:
                    continue

            start += batch_size

        return dsa
