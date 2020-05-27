"""block runner"""
from dataclasses import dataclass
from typing import List, Union

import gc
import networkx as nx
import pandas as pd
from sklearn.exceptions import NotFittedError

from .backends.experiments import LocalExperimentBackend, ExperimentBackend
from .core import BaseBlock
from .utils import get_logger, timer

logger = get_logger(__name__)


def check_block_fit_output(output_df, input_df):
    if not isinstance(output_df, pd.DataFrame):
        raise ValueError('Block output must be pandas dataframe object. Actually: {}'.format(type(output_df)))


def execute_fit(block, source_df, y, experiment) -> pd.DataFrame:
    with experiment.mark_time('fit'):
        experiment.logger.info(f'start fit {block.name}')
        out_df = block.fit(source_df=source_df,
                           y=y,
                           experiment=experiment)

    check_block_fit_output(out_df, source_df)
    block.report(source_df=source_df,
                 y=y,
                 out_df=out_df,
                 experiment=experiment)

    if experiment.can_save:
        block.frozen(experiment)
        block.clear_fit_cache()
    return out_df


def execute_transform(block, source_df, experiment) -> pd.DataFrame:
    if experiment.can_save:
        # run transform, load data from experiment
        block.unzip(experiment)
    if not block.check_is_fitted(experiment):
        raise NotFittedError(
            'try to execute transform using {} but it is not fitted yet in the current environment. '.format(
                block.name) + \
            'for predict block pass `check_is_fitted` == True after load `unzip` method.'
            ' Check the directory - {} '.format(experiment.namespace)
        )
    out_df = block.transform(source_df)
    return out_df


def sort_blocks(blocks: List[BaseBlock]):
    blocks = set([x for b in blocks for x in b.all_network_blocks()])
    blocks = list(blocks)

    def get_index(b):
        return blocks.index(b)

    G = nx.DiGraph()
    for block in blocks:
        G.add_node(get_index(block), name=block.name)

    for block in blocks:
        for p in block.parent_blocks:
            G.add_edge(
                get_index(p), get_index(block)
            )

    for i in list(nx.topological_sort(G)):
        yield blocks[i]


@dataclass
class EstimatorResult:
    oof_df: pd.DataFrame
    block: BaseBlock


def _to_check(done):
    if done:
        return '[x]'
    return '[ ]'


def create_source_df(block, input_df, output_caches, experiment, storage_key, is_fit_context):
    if not block.has_parent:
        return input_df

    source_df = pd.DataFrame()
    for b in block.parent_blocks:
        if b.runtime_env in output_caches:
            _df = output_caches.get(b.runtime_env)
        else:
            with experiment.as_environment(b.runtime_env) as exp:
                _df = b.load_output_from_storage(
                    storage_key=storage_key,
                    experiment=exp,
                    is_fit_context=is_fit_context)
        _df = _df.add_prefix(f'{b.name}__')
        source_df = pd.concat([source_df, _df], axis=1)
    return source_df


@dataclass
class Task:
    order_index: int
    block: BaseBlock
    run_fit: bool = False
    completed: bool = False

    def __str__(self):
        return f'- {self.order_index:02d} {_to_check(self.completed)} {_to_check(self.run_fit)} {self.block.name}' + \
               ' | parents ' + ' / '.join(map(str, self.block.parent_blocks))

    def changed_blocks_in_parents(self, tasks: List['Task']) -> List[BaseBlock]:
        retval = []
        for task in tasks:
            if not task.run_fit:
                continue

            if task.block in self.block.parent_blocks:
                retval += [task.block]
        return retval

    def run(self,
            input_df,
            y,
            is_fit_context,
            experiment: LocalExperimentBackend,
            ignore_cache,
            output_caches):

        storage_key = 'train_output' if is_fit_context else 'test_output'
        block = self.block
        if is_fit_context:
            with experiment.as_environment(block.runtime_env) as exp:
                if block.check_is_fitted(exp) and exp.has(storage_key):
                    if not ignore_cache:
                        logger.info(
                            'already fitted and exist output files. use these cache files at {}'.format(exp.output_dir))
                        self.completed = True
                        self.run_fit = False
                        return exp.load_object(storage_key)

                    logger.debug('already exist trained files, but ignore these files. retrain')

        source_df = create_source_df(self.block, input_df, output_caches=output_caches, experiment=experiment,
                                     storage_key=storage_key, is_fit_context=is_fit_context)

        with experiment.as_environment(block.runtime_env) as exp:
            if is_fit_context:
                with exp.mark_time('fit'):
                    out_df = execute_fit(block, source_df, y, exp)
                self.run_fit = True
            else:
                out_df = execute_transform(block, source_df, exp)

            logger.info('save output to storage')
            exp.save_as_python_object(storage_key, out_df)

        self.completed = True
        del source_df
        gc.collect()
        return out_df


class Runner:
    def __init__(self, blocks: Union[BaseBlock, List[BaseBlock]], experiment=None):
        if isinstance(blocks, BaseBlock):
            blocks = [blocks]

        self.blocks = blocks

        if experiment is None:
            experiment = LocalExperimentBackend()
        self.experiment = experiment

    def fit(self,
            train_df,
            y=None,
            cache: bool = True,
            ignore_past_log=False):

        estimator_predicts = self._run(
            input_df=train_df,
            y=y,
            experiment=self.experiment,
            cache=cache,
            ignore_cache=ignore_past_log,
            is_fit_context=True,
        )

        oof_df = pd.DataFrame()
        for p in estimator_predicts:
            oof_df[p.block.runtime_env] = p.oof_df.values[:, 0]
        self.experiment.save_dataframe('out_of_folds', oof_df)
        return estimator_predicts

    def predict(self,
                input_df,
                cache: bool = True):
        estimator_predicts = self._run(
            input_df=input_df,
            y=None,
            experiment=self.experiment,
            cache=cache,
            is_fit_context=False
        )

        return estimator_predicts

    def _run(self,
             input_df,
             y,
             experiment: LocalExperimentBackend = None,
             is_fit_context=False,
             cache=True,
             ignore_cache=False) -> List[EstimatorResult]:
        blocks = list(sort_blocks(self.blocks))
        output_caches = {}
        estimator_predicts = []
        tasks = [Task(i + 1, b) for i, b in enumerate(blocks)]

        self.show_tasks(tasks)

        for i, task in enumerate(tasks):

            changed_blocks = task.changed_blocks_in_parents(tasks)
            if len(changed_blocks) > 0:
                logger.info('related blocks has changed. so run ignore cache context. / ' +
                            ','.join(map(str, changed_blocks)))

            with timer(logger, prefix=task.block.name + ' '):
                out_df = task.run(input_df=input_df, y=y, is_fit_context=is_fit_context, experiment=experiment,
                                  ignore_cache=ignore_cache or len(changed_blocks) > 0,
                                  output_caches=output_caches)

            if cache:
                output_caches[task.block.runtime_env] = out_df

            if task.block.is_estimator:
                estimator_predicts += [EstimatorResult(oof_df=out_df, block=task.block)]

        self.show_tasks(tasks)

        return estimator_predicts

    def show_tasks(self, tasks):
        logger.info('=' * 40)
        logger.info('> task status')
        for task in tasks:
            logger.info(str(task))


def create_runner(blocks, experiment=None) -> Runner:
    if experiment is None:
        experiment = ExperimentBackend()
    return Runner(blocks, experiment)