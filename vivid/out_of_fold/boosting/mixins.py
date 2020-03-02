import os
from copy import deepcopy
from typing import List

import matplotlib.pyplot as plt
from optuna.trial import Trial

from vivid.sklearn_extend import PrePostProcessModel
from vivid.visualize import visualize_feature_importance
from ..base import BaseOutOfFoldFeature


class FeatureImportanceMixin:
    fitted_models: List[PrePostProcessModel]
    n_importance_plot = 50

    def after_kfold_fitting(self, df_source, y, predict):
        self.logger.info(f'save to {self.output_dir}')

        if self.is_recording:
            fig, ax, importance_df = visualize_feature_importance(self.fitted_models,
                                                                  columns=df_source.columns,
                                                                  top_n=self.n_importance_plot,
                                                                  plot_type='boxen')
            importance_df.to_csv(os.path.join(self.output_dir, 'feature_importance.csv'), index=False)
            fig.savefig(os.path.join(self.output_dir, 'boxen_feature_importance.png'), dpi=120)

            plt.close(fig)

        super(FeatureImportanceMixin, self).after_kfold_fitting(df_source, y, predict)


class BoostingEarlyStoppingMixin:
    early_stopping_rounds = 100
    eval_metric = None
    fit_verbose = 100

    def fit_model(self, X, y, model_params, x_valid, y_valid, cv):
        """
        `PrePostProcessModel` を学習させます.
        recordable_model_params には target/input に関するスケーリングを含めたパラメータ情報を与えてください

        Args:
            X: 特徴量
            y: ターゲット変数
            model_params(dict):
            prepend_name(str):

        Returns:

        """
        model_params = deepcopy(model_params)
        eval_metric = model_params.pop('eval_metric', self.eval_metric)
        model = self.create_model(model_params, prepend_name=str(cv),
                                  recording=cv is not None)  # type: PrePostProcessModel

        # hack: validation data に対して transform が聞かないため, before fit で学習して fit 前に変換を実行する
        model._before_fit(X, y)
        x_valid = model.input_transformer.transform(x_valid)
        y_valid = model.target_transformer.transform(y_valid)
        model.fit(X, y,
                  eval_set=[(x_valid, y_valid)],
                  early_stopping_rounds=self.early_stopping_rounds,
                  eval_metric=eval_metric,
                  verbose=None if cv is None else self.fit_verbose)
        return model


class BoostingOufOfFoldFeatureSet(FeatureImportanceMixin, BoostingEarlyStoppingMixin, BaseOutOfFoldFeature):
    pass


def get_boosting_parameter_suggestions(trial: Trial) -> dict:
    """
    Get parameter sample for Boosting (like XGBoost, LightGBM)

    Args:
        trial(trial.Trial):

    Returns:
        dict: parameter sample generated by trial object
    """
    return {
        # L2 正則化
        'reg_lambda': trial.suggest_loguniform('reg_lambda', 1e-3, 1e3),
        # L1 正則化
        'reg_alpha': trial.suggest_loguniform('reg_alpha', 1e-3, 1e3),
        # 弱学習木ごとに使う特徴量の割合
        # 0.5 だと全体のうち半分の特徴量を最初に選んで, その範囲内で木を成長させる
        'colsample_bytree': trial.suggest_loguniform('colsample_bytree', .5, 1.),
        # 学習データ全体のうち使用する割合
        # colsample とは反対に row 方向にサンプルする
        'subsample': trial.suggest_loguniform('subsample', .5, 1.),
        # 木の最大の深さ
        # たとえば 5 の時各弱学習木のぶん機は最大でも5に制限される.
        'max_depth': trial.suggest_int('max_depth', low=3, high=8),
        # 末端ノードに含まれる最小のサンプル数
        # これを下回るような分割は作れなくなるため, 大きく設定するとより全体の傾向でしか分割ができなくなる
        # [NOTE]: 数であるのでデータセットの大きさ依存であることに注意
        'min_child_weight': trial.suggest_uniform('min_child_weight', low=.5, high=40)
    }