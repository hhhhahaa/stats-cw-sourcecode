import datetime
import numpy as np
import pandas_datareader as pdr
from esig import tosig
from tqdm.auto import tqdm
from sklearn.preprocessing import MinMaxScaler
import pandas as pd

from utils.leadlag import leadlag
from cvae import CVAE
from rough_bergomi import rough_bergomi

class MarketGenerator:
    def __init__(self, start=datetime.date(2000, 1, 1),
                 end=datetime.date(2019, 1, 1), freq="M",
                 sig_order=4, rough_bergomi=None, 
                 data_path = data_path, index_col = 'Date',
                 usefcols = ['Date','Price'], dateformat = '%m/%d/%Y'):

        self.ticker = ticker
        self.start = start
        self.end = end
        self.freq = freq
        self.order = sig_order
        self.dataPath = data_path
        self.index_col = index_col
        self.usecols = usefulcols
        self.dateformat = dateformat

        if rough_bergomi:
             self._load_rough_bergomi(rough_bergomi)
        else:
            self._load_data()

        self._build_dataset()
        self.generator = CVAE(n_latent=8, alpha=0.003)

    def _load_rough_bergomi(self, params):
        grid_points_dict = {"M": 28, "W": 5, "Y": 252}
        grid_points = grid_points_dict[self.freq]
        params["T"] = grid_points / grid_points_dict["Y"]

        paths = rough_bergomi(grid_points, **params)

        self.windows = [leadlag(path) for path in paths]


    def _load_data(self):
      self.data = pd.read_csv(self.dataPath, index_col = self.index, 
      usecols = self.usecols)
      self.data.index = pd.to_datetime(self.data.index,format=self.dateformat)
      if isinstance(self.data.iloc[1,0], str):
        self.data.iloc[:,0] = [x.replace(',', '') for x in self.data.iloc[:,0]]
        self.data.iloc[:,0] = [float(x) for x in self.data.iloc[:,0]]
        # try:
        #     # self.data = pdr.get_data_yahoo(self.ticker, self.start, self.end)["Close"]
        #     # self.data = web.get_data_yahoo(self.ticker, self.start, self.end)["Close"]
        # except:
        #     raise RuntimeError(f"Could not download data for {self.ticker} from {self.start} to {self.end}.")

      self.windows = []
      for _, window in self.data.resample(self.freq):
          values = window.values# / window.values[0]
          path = leadlag(values)

          self.windows.append(path)

    def _logsig(self, path):
        return tosig.stream2logsig(path, self.order)

    def _build_dataset(self):
        if self.order:
            self.orig_logsig = np.array([self._logsig(path) for path in tqdm(self.windows, desc="Computing log-signatures")])
        else:
            self.orig_logsig = np.array([np.diff(np.log(path[::2, 1])) for path in self.windows])

            self.orig_logsig = np.array([p for p in self.orig_logsig if len(p) >= 4])
            steps = min(map(len, self.orig_logsig))
            self.orig_logsig = np.array([val[:steps] for val in self.orig_logsig])

        self.scaler = MinMaxScaler(feature_range=(0.00001, 0.99999))
        logsig = self.scaler.fit_transform(self.orig_logsig)

        self.logsigs = logsig[1:]
        self.conditions = logsig[:-1]


    def train(self, n_epochs=10000):
        self.generator.train(self.logsigs, self.conditions, n_epochs=n_epochs)

    def generate(self, logsig, n_samples=None, normalised=False):
        generated = self.generator.generate(logsig, n_samples=n_samples)

        if normalised:
            return generated

        if n_samples is None:
            return self.scaler.inverse_transform(generated.reshape(1, -1))[0]

        return self.scaler.inverse_transform(generated)
