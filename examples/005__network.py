import pandas as pd

from vivid import create_runner
from vivid.backends.experiments import LocalExperimentBackend
from vivid.core import BaseBlock


class TestBlock(BaseBlock):
    def fit(self, source_df, y, experiment: LocalExperimentBackend) -> pd.DataFrame:
        print(experiment.output_dir, self.runtime_env)
        return source_df

    def transform(self, source_df):
        return source_df


if __name__ == '__main__':
    a = TestBlock('a')
    b = TestBlock('b')
    c = TestBlock('c')

    d = TestBlock('d', parent=[a, b, c])
    e = TestBlock('e', parent=[a, c])
    f = TestBlock('f', parent=[e, b, d])

    g = TestBlock('g', parent=[f, e, a, c, d])

    exp = LocalExperimentBackend(to='./outputs/test')
    input_df = pd.DataFrame()

    runner = create_runner(g, experiment=exp)
    runner.fit(input_df)
    runner.predict(input_df)
