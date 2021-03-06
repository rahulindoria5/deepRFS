import gc
import glob

import numpy as np
from keras import backend as K

from deep_rfs.extraction.GenericEncoder import GenericEncoder


class NNStack:
    def __init__(self):
        self.stack = []
        self.support_dim = 0

    def add(self, model, support):
        """
        Add feature extractor and its support to the stack
        :param model: feature extractor
        :param support: np.array, a boolean mask to use as support for the extractor
        """
        d = {'model': model, 'support': np.array(support)}
        self.stack.append(d)
        self.support_dim += d['support'].sum()

    def s_features(self, x):
        """
        Runs all neural networks on the given state, returns the selected
        features of each NN as a single array.
        :param x: a state
        """
        if x.shape[0] == 1:
            output = []
        else:
            output = np.empty((x.shape[0], 0))

        for idx, d in enumerate(self.stack):
            prediction = d['model'].s_features(x, d['support'])
            if prediction.ndim == 1:
                output = np.concatenate([output, prediction])
            else:
                output = np.column_stack((output, prediction))
        return np.array(output)

    def model_s_features(self, x, index):
        """
        Returns the features of the model at the given index in the stack
        :param x: a state
        :param index: int, index of the model to use
        :return: 
        """
        d = self.stack[index]
        return d['model'].s_features(x, d['support'])

    def get_model(self, index):
        """
        :param index:  int, index of the model to return
        :return: the model at the given index in the stack
        """
        return self.stack[index]['model']

    def get_support(self, index):
        """
        :param index:  int, index of the model to return
        :return: the support associated to the model at the given index in the stack
        """
        return self.stack[index]['support']

    def get_support_dim(self, index=None):
        """
        :param index: int, index of the model to consider
        :return: the cumulative dimension of all supports in the stack, or the
        dimension of the index-th support if index is given.
        """
        if index is None:
            return sum([d['support'].sum() for d in self.stack])
        else:
            return self.stack[index]['support'].sum()

    def reset(self):
        """
        Empties the stack and forcibly frees memory.
        """
        self.stack = []
        self.support_dim = 0
        K.clear_session()
        gc.collect()

    def save(self, folder):
        """
        Saves the encoders of all models in the stack and their supports
        in folder, as .h5 and .npy files respectively.
        :param folder: string, path to the folder in which to save the models
        """
        if not folder.endswith('/'):
            folder += '/'
        for idx, d in enumerate(self.stack):
            d['model'].save_encoder(folder + 'encoder_%d.h5' % idx)
            np.save(folder + 'support_%d.npy' % idx, d['support'])

    def load(self, folder):
        """
        Loads all models (as .h5 files) and their supports (as .npy files) from
        folder.
        Note that the loaded models are instantiated as GenericEncoder models
        and are not trainable.
        :param folder: string, path to the folder from which to load the models
        """
        # Get all filepaths
        models = glob.glob(folder + 'encoder_*.h5')
        supports = glob.glob(folder + 'support_*.npy')
        nb_models = len(models)
        nb_supports = len(supports)
        assert nb_models == nb_supports and nb_models != 0

        self.reset()

        # Build all models (and their supports) for the stack
        for i in range(nb_models):
            m = GenericEncoder(folder + 'encoder_%s.h5' % i)
            s = np.load(folder + 'support_%s.npy' % i)
            self.stack.append({'model': m, 'support': s})

        self.support_dim = self.get_support_dim()
