from copy import deepcopy

from sklearn.svm import SVC, SVR

from .base import BaseOutOfFoldFeature, BaseOptunaOutOfFoldFeature

SVM_DEFAULT_PARAMS = {
    'C': 0.1,
    'kernel': 'rbf',
    'shrinking': True,
    'gamma': 'auto',
    'probability': True,
    'random_state': 19,
    'input_scaling': 'standard',
}


class SVCOutOfFold(BaseOutOfFoldFeature):
    model_class = SVC
    initial_params = deepcopy(SVM_DEFAULT_PARAMS)


class SVROutOfFold(BaseOutOfFoldFeature):
    model_class = SVR
    initial_params = {
        'input_scaling': 'standard'
    }


def get_default_parameter_suggestions(trial):
    params = {
        'C': trial.suggest_loguniform('C', 1e-3, 1e2),
        'kernel': trial.suggest_categorical('kernel', ['rbf', 'poly', 'sigmoid', 'linear']),
        'gamma': trial.suggest_categorical('gamma', ['auto', 'scale']),
    }

    if params['kernel'] == 'poly':
        params['degree'] = trial.suggest_int('degree', 2, 4)

    return params


class SVCOptunaOutOfFold(BaseOptunaOutOfFoldFeature):
    model_class = SVC
    initial_params = deepcopy(SVM_DEFAULT_PARAMS)
    optuna_jobs = 1

    def generate_model_class_try_params(self, trial):
        params = get_default_parameter_suggestions(trial)
        return params


class SVROptunaOutOfFold(BaseOptunaOutOfFoldFeature):
    model_class = SVR
    optuna_jobs = 1
    initial_params = {
        'input_scaling': 'standard'
    }

    def generate_model_class_try_params(self, trial):
        params = get_default_parameter_suggestions(trial)
        params['epsilon'] = trial.suggest_loguniform('epsilon', 1e-3, 1e2)
        return params
