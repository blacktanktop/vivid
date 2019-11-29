import os

import numpy as np
import pandas as pd

from vivid.core import AbstractFeature

RECORDING_DIR = '/workspace/output'
os.makedirs(RECORDING_DIR, exist_ok=True)


class SampleFeature(AbstractFeature):
    def __init__(self):
        super(SampleFeature, self).__init__('sample')

    def call(self, df_source, y=None, test=False):
        return df_source


class RecordingFeature(AbstractFeature):
    def __init__(self):
        super(RecordingFeature, self).__init__(name='rec_sample', parent=None, root_dir=RECORDING_DIR)

    def call(self, df_source, y=None, test=False):
        return df_source


n_rows = 100
n_cols = 10
x = np.random.uniform(size=(n_rows, n_cols))
y = np.random.uniform(size=(n_rows,))
df_train = pd.DataFrame(x)


def test_sample_feature():
    feat = SampleFeature()
    df = feat.fit(df_train, y=y)
    assert len(df) == len(df_train)
