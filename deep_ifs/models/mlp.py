from keras.models import Sequential
from keras.layers import Dense
from keras.callbacks import EarlyStopping
from sklearn.metrics import r2_score


class MLP:
    def __init__(self, input_shape, output_size, layers=(512,), activation='relu', output_activation=None, optimizer='adam', loss='mse'):
        self.model = Sequential()
        if isinstance(input_shape, tuple):
            self.input_shape = input_shape
        else:
            self.input_shape = (input_shape, )
        self.model.add(Dense(layers[0], activation=activation, input_shape=self.input_shape))
        if len(layers) > 1:
            for l in layers[1:]:
                self.model.add(Dense(l, activation=activation))
        self.model.add(Dense(output_size, activation=output_activation))
        self.model.compile(optimizer=optimizer, loss=loss)

    def fit(self, X, Y, epochs=10, patience=2, validation_data=None, validation_split=None, **kwargs):
        if validation_data is not None:
            es = EarlyStopping(patience=patience)
        else:
            es = None
        return self.model.fit(X, Y,
                              epochs=epochs,
                              callbacks=[es],
                              validation_data=validation_data,
                              validation_split=validation_split,
                              **kwargs)

    def predict(self, X, **kwargs):
        return self.model.predict(X, **kwargs)

    def score(self, X, Y, multioutput='uniform_average'):
        return r2_score(Y, self.model.predict(X), multioutput=multioutput)
