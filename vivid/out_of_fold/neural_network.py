from typing import Tuple

import numpy as np
from keras.callbacks import ReduceLROnPlateau
from sklearn.utils import class_weight

from vivid.out_of_fold.base import BaseOutOfFoldFeature
from vivid.sklearn_extend.neural_network import SkerasClassifier, SkerasRegressor, ROCAucCallback


class SkerasOutOfFoldMixin:
    initial_params = {
        'input_scaling': True,
        'epochs': 30,
        'batch_size': 128,
        'workers': -1
    }

    def get_fit_params_on_each_fold(self, model_params: dict,
                                    training_set: Tuple[np.ndarray, np.ndarray],
                                    validation_set: Tuple[np.ndarray, np.ndarray],
                                    indexes_set: Tuple[np.ndarray, np.ndarray]) -> dict:
        params = super() \
            .get_fit_params_on_each_fold(model_params, training_set, validation_set, indexes_set)
        callbacks = [
            ROCAucCallback(training_data=training_set, validation_data=validation_set),
            ReduceLROnPlateau(patience=5, verbose=1)
        ]

        add_params = {
            'callbacks': callbacks,
            'validation_data': validation_set,
        }

        params.update(add_params)
        return params


class SkerasClassifierOutOfFoldFeature(SkerasOutOfFoldMixin, BaseOutOfFoldFeature):
    model_class = SkerasClassifier

    def get_fit_params_on_each_fold(self, model_params: dict,
                                    training_set: Tuple[np.ndarray, np.ndarray],
                                    validation_set: Tuple[np.ndarray, np.ndarray],
                                    indexes_set: Tuple[np.ndarray, np.ndarray]) -> dict:
        params = super(SkerasClassifierOutOfFoldFeature, self) \
            .get_fit_params_on_each_fold(model_params, training_set, validation_set, indexes_set)

        y = training_set[1]
        weight = class_weight.compute_class_weight('balanced', np.unique(y), y)
        params['class_weight'] = weight
        return params


class SkerasRegressorOutOfFoldFeature(BaseOutOfFoldFeature):
    model_class = SkerasRegressor
