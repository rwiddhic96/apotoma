"""Stages:

    0. Function to generate ground truths:
        Input: model, x_test, test_pred
        Output: 1-D binary array, 1 if classified correctly, zero if classified incorrectly

    1. Function to create sub-models
    Input: model (trained), list of layer numbers, no. of output nodes (num_classes)
    Output: list of sub_models

    2. Function to train sub models (Only final layer connections to fully connected). Freeze other weights.
        Input: list of sub_models, x_train
        Output: list of trained sub_models

        Number of epochs? Unclear, paper does not specify.

    3. Function to calculate prediction profile: One softmax vector per sub-model
        Input: List of trained sub_models
        Outputs: k Array of softmax arrays, one for each sub_model, shape: #classes * #sub_models

    4. Function to calculate SV score
        Input: a) k array of softmax arrays, one for each sub_model, shape: #classes * #sub_models
               b) train_pred: Array of training predictions of original model M

        Output: Array of SV scores of length k, hopefully ordered by shallow to deep sub models.

    5. Function to calculate PV score for all x_test
        Input: a) x_test, array_sv_score, weights_array
        Output: Array of PV scores in (0,1).

    6. Function to calculate weights array [3 options: Logarithmic, Linear, Exponential]:
        Input: a) Type of weight growth
               b) Number k of specific layer

        Output: array of weights, shape: (#sub_models,)

    7. Function calculate AUC score:
        Inputs: a) generate_ground_truth(model, test_pred, x_test)
                b) PV score array
        Output: roc_auc_score(labels, pv_score_array)
    """

import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.models import load_model
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import ZeroPadding2D, Dense, Flatten
import os

class Dissector():

    def __init__(self, model: tf.keras.Model, args: {}):

        self.model = model
        self.args = args

    def generate_ground_truth(self, model: tf.keras.Model , x_test: tf.data.Dataset, y_test: tf.data.Dataset):

        #model = load_model(self.args['model_path'])
        test_preds = model.predict_classes(x_test)
        labels = np.argmax(y_test, axis=1)
        corr = np.where(test_preds == labels)
        incorr = np.where(test_preds != labels)
        labels[corr] = 1
        labels[incorr] = 0

        return labels

    def generate_sub_models(self, layer_list: [], model: tf.keras.Model):

        for i, l in enumerate(layer_list):
            n_model = Sequential()
            for layer in model.layers[0:l]:
                n_model.add(layer)

            n_model.add(Flatten())
            for layer in n_model.layers:
                layer.trainable = False

            n_model.add(Dense(10, activation='softmax'))
            n_model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])
            n_model.save("./submodels_dissector/model/submodel_{}_lenet4_{}.h5".format(i, 'mnist'))
            print("Submodels generated for required layers: {}".format(layer_list))

    def train_sub_models(self, submodel_path: str, x_train: tf.data.Dataset, y_train: tf.data.Dataset, epochs: int):

        sub_models = os.listdir(submodel_path)

        for i, m in enumerate(sub_models):
            s_model = load_model(m)
            s_model.fit(
                x_train,
                y_train,
                epochs=epochs,
                batch_size=128,
                shuffle=True,
                verbose=1,
                validation_split=0.2,
            )

            s_model.save("./submodels_dissector/model/submodel_{}_lenet4_{}.h5".format(i, 'mnist'))
            print("Stored trained submodels_dissector on the same directory")


