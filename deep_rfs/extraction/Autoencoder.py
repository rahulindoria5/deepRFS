from operator import mul

from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras.layers import *
from keras.metrics import binary_crossentropy
from keras.models import Model
from keras.optimizers import *
from keras.regularizers import l1


class Autoencoder:
    def __init__(self, input_shape, n_features=128, batch_size=32,
                 nb_epochs=10, dropout_prob=0.5, binarize=False,
                 binarization_threshold=0.1,
                 class_weight=None, sample_weight=None, load_path=None,
                 logger=None, ckpt_file=None, use_contractive_loss=False,
                 use_vae=False, beta=1., use_dense=False):
        """
        :param input_shape: input shape for the Keras model 
        :param n_features: number of features in the innermost layer
        :param batch_size: number of samples in a batch
        :param nb_epochs: number of epochs to train for
        :param dropout_prob: dropout probability for the dense layer (requires to set use_dense)
        :param binarize: whether to convert the input space to binary
        :param binarization_threshold: threshold to define binarization from greyscale
        :param class_weight: class weights for training the model
        :param sample_weight: sample weights for training the model
        :param load_path: path to file with saved weights
        :param logger: Logger instance for logging
        :param ckpt_file: file to save the model to
        :param use_contractive_loss: whether to use a contractive loss during training (i.e. make it a contractive AE)
        :param use_vae: whether to make the AE a VAE
        :param beta: beta parameter for beta-VAE setting
        :param use_dense: whether to use an inner dense layer
        """
        self.input_shape = input_shape
        self.input_dim_full = reduce(mul, input_shape)
        self.n_features = n_features
        self.batch_size = batch_size
        self.nb_epochs = nb_epochs
        self.dropout_prob = dropout_prob
        self.binarize = binarize
        self.binarization_threshold = binarization_threshold
        self.class_weight = class_weight
        self.sample_weight = sample_weight
        self.logger = logger
        self.decoding_available = False
        self.use_contractive_loss = use_contractive_loss
        self.use_vae = use_vae
        self.beta = beta
        self.use_dense = use_dense
        self.support = None

        # Check flag consistency
        assert self.use_contractive_loss + self.use_vae + self.use_dense <= 1, 'Set at most one flag for contractive, VAE or dense'

        # Callbacks
        self.es = EarlyStopping(monitor='val_loss', min_delta=1e-5, patience=2)

        if ckpt_file is not None:
            self.ckpt_file = ckpt_file if logger is None else (logger.path + ckpt_file)
        else:
            self.ckpt_file = 'NN.h5' if logger is None else (logger.path + 'NN.h5')
        self.mc = ModelCheckpoint(self.ckpt_file, monitor='val_loss',
                                  save_best_only=True, save_weights_only=True,
                                  verbose=0)

        # Build network
        self.input = Input(shape=(4, 108, 84))

        self.encoded = Conv2D(32, (8, 8), padding='valid',
                              activation='relu', strides=(4, 4),
                              data_format='channels_first')(self.input)

        self.encoded = Conv2D(64, (4, 4), padding='valid',
                              activation='relu', strides=(2, 2),
                              data_format='channels_first')(self.encoded)

        self.encoded = Conv2D(64, (3, 3), padding='valid',
                              activation='relu', strides=(1, 1),
                              data_format='channels_first')(self.encoded)

        self.encoded = Conv2D(16, (3, 3), padding='valid',
                              activation='relu', strides=(1, 1),
                              data_format='channels_first',
                              name='to_flatten')(self.encoded)

        self.features = Flatten()(self.encoded)

        if self.use_contractive_loss:
            self.features = Dense(self.n_features, activation='relu',
                                  name='features')(self.features)
        elif self.use_vae:
            self.z_mean = Dense(self.n_features, activation='linear')(self.features)
            self.z_log_var = Dense(self.n_features,
                                   activation='linear')(self.features)

            def sample_z(args):
                z_mean, z_log_var = args
                eps = K.random_normal(shape=(K.shape(z_mean)[0], self.n_features),
                                      mean=0.,
                                      stddev=1.)
                return z_mean + K.exp(z_log_var) * eps

            self.features = Lambda(sample_z,
                                   name='features')([self.z_mean, self.z_log_var])
        elif self.use_dense:
            self.features = Dense(self.n_features, activation='relu', activity_regularizer=l1(1e-05))(self.features)
            self.features = Dropout(self.dropout_prob,
                                    name='features')(self.features)

        if (self.n_features != 16 * 8 * 5) and (self.use_vae or self.use_dense or self.use_contractive_loss):
            # This layer is used before the decoder to bring the number of activations back to 640
            self.pre_decoder = Dense(16 * 8 * 5, activation='relu')(self.features)
        else:
            self.pre_decoder = self.features

        # Decoded
        self.decoded = Reshape((16, 8, 5))(self.pre_decoder)

        self.decoded = Conv2DTranspose(16, (3, 3), padding='valid',
                                       activation='relu', strides=(1, 1),
                                       data_format='channels_first')(self.decoded)

        self.decoded = Conv2DTranspose(64, (3, 3), padding='valid',
                                       activation='relu', strides=(1, 1),
                                       data_format='channels_first')(self.decoded)

        self.decoded = Conv2DTranspose(64, (4, 4), padding='valid',
                                       activation='relu', strides=(2, 2),
                                       data_format='channels_first')(self.decoded)

        self.decoded = Conv2DTranspose(32, (8, 8), padding='valid',
                                       activation='relu', strides=(4, 4),
                                       data_format='channels_first')(self.decoded)

        self.decoded = Conv2DTranspose(4, (1, 1), padding='valid',
                                       activation='sigmoid', strides=(1, 1),
                                       data_format='channels_first')(self.decoded)

        # Models
        self.model = Model(inputs=self.input, outputs=self.decoded)
        self.encoder = Model(inputs=self.input, outputs=self.features)

        # Build decoder model
        if self.decoding_available:
            self.encoded_input = Input(shape=(16 * 8 * 5,))
            self.decoding_intermediate = self.model.layers[-6](self.encoded_input)
            self.decoding_intermediate = self.model.layers[-5](self.decoding_intermediate)
            self.decoding_intermediate = self.model.layers[-4](self.decoding_intermediate)
            self.decoding_intermediate = self.model.layers[-3](self.decoding_intermediate)
            self.decoding_intermediate = self.model.layers[-2](self.decoding_intermediate)
            self.decoding_output = self.model.layers[-1](self.decoding_intermediate)
            self.decoder = Model(input=self.encoded_input, output=self.decoding_output)

        # Optimization algorithm
        self.optimizer = Adam()

        # Load the network from saved model
        if load_path is not None:
            self.load(load_path)

        if self.use_contractive_loss:
            def contractive_loss(y_pred, y_true):
                y_true = K.batch_flatten(y_true)
                y_pred = K.batch_flatten(y_pred)
                xent = binary_crossentropy(y_pred, y_true)

                W = K.variable(value=self.model.get_layer('features').get_weights()[0])  # N x N_hidden
                W = K.transpose(W)  # N_hidden x N
                h = self.model.get_layer('features').output
                dh = h * (1 - h)  # N_batch x N_hidden

                # N_batch x N_hidden * N_hidden x 1 = N_batch x 1
                contractive = 1e-03 * K.sum(dh ** 2 * K.sum(W ** 2, axis=1), axis=1)

                return xent + contractive

            self.loss = contractive_loss
        elif self.use_vae:
            def vae_loss(y_true, y_pred):
                y_true = K.flatten(y_true)
                y_pred = K.flatten(y_pred)
                xent = self.input_dim_full * binary_crossentropy(y_pred, y_true)
                kl = - 0.5 * K.sum(1 + self.z_log_var - K.square(self.z_mean) - K.exp(self.z_log_var), axis=-1)

                return K.mean(xent + self.beta * kl)

            self.loss = vae_loss
        else:
            self.loss = 'binary_crossentropy'

        self.model.compile(optimizer=self.optimizer, loss=self.loss,
                           metrics=['accuracy'])

    def preprocess_state(self, x, binarize=False, binarization_threshold=0.1):
        """
        :param x: np.array, a batch of states 
        :param binarize: whether to convert states to a {0, 1} binary space
        :param binarization_threshold: threshold for binarization
        :return: the preprocessed state
        """
        if not x.shape[1:] == (4, 108, 84):
            x = x[:, :, 2:, :]
            assert x.shape[1:] == (4, 108, 84)
        x = np.asarray(x).astype('float32') / 255.  # To 0-1 range
        if binarize:
            x[x < binarization_threshold] = 0
            x[x >= binarization_threshold] = 1

        return x

    def fit(self, x, y, validation_data=None):
        """
        :param x: samples on which to train
        :param y: targets on which to train
        :param validation_data: tuple (X, Y) to use as validation data
        :return: the metrics of interest as defined in the model
        """

        # Preprocess training data
        x_train = self.preprocess_state(np.asarray(x), binarize=self.binarize, binarization_threshold=self.binarization_threshold)
        y_train = self.preprocess_state(np.asarray(y), binarize=self.binarize, binarization_threshold=self.binarization_threshold)

        # Preprocess validation data
        if validation_data is not None:
            val_x = self.preprocess_state(validation_data[0], binarize=self.binarize, binarization_threshold=self.binarization_threshold)
            val_y = self.preprocess_state(validation_data[1], binarize=self.binarize, binarization_threshold=self.binarization_threshold)
            validation_data = (val_x, val_y)

        return self.model.fit(x_train, y_train,
                              class_weight=self.class_weight,
                              sample_weight=self.sample_weight,
                              epochs=self.nb_epochs,
                              validation_data=validation_data,
                              callbacks=[self.es, self.mc])

    def fit_generator(self, generator, steps_per_epoch, nb_epochs, validation_data=None):
        """
        :param generator: generator for batch data 
        :param steps_per_epoch: how many batches in an epoch
        :param nb_epochs: how many epochs to train for
        :param validation_data: tuple (X, Y) to use as validation data (it will be preprocessed)
        :return: 
        """
        # Preprocess validation data
        if validation_data is not None:
            val_x = self.preprocess_state(validation_data[0], binarize=self.binarize, binarization_threshold=self.binarization_threshold)
            val_y = self.preprocess_state(validation_data[1], binarize=self.binarize, binarization_threshold=self.binarization_threshold)
            validation_data = (val_x, val_y)

        return self.model.fit_generator(generator,
                                        steps_per_epoch,
                                        epochs=nb_epochs,
                                        max_q_size=250,
                                        callbacks=[self.es, self.mc],
                                        validation_data=validation_data)

    def predict(self, x):
        """
        :param x: a batch of samples on which to predict
        :return: the predictions on the batch
        """
        # Feed input to the model, return encoded and re-decoded images
        x_test = self.preprocess_state(x, binarize=self.binarize, binarization_threshold=self.binarization_threshold)
        pred = self.model.predict(x_test)

        return pred

    def all_features(self, x):
        """ Embeds the given array using the encoder
        :param x: samples to encode, ignoring the support 
        :return: the encoded samples
        """
        # Feed input to the model, return encoded images flattened
        x = self.preprocess_state(x, binarize=self.binarize, binarization_threshold=self.binarization_threshold)

        if x.shape[0] == 1:
            # x is a singe sample
            return np.asarray(self.encoder.predict_on_batch(x)).flatten()
        else:
            return np.asarray(self.encoder.predict(x))

    def s_features(self, x, support=None):
        """
        Runs the given samples on the model and returns the features of the last
        dense layer filtered by the support mask.
        :param x: samples to encode
        :param support: boolean mask with which to filter the embedding
        :return: th encoded samples
        """
        if support is None:
            if self.support is None:
                support = np.array([True] * self.get_features_number())
            else:
                support = self.support

        prediction = self.all_features(x)
        if x.shape[0] == 1:
            # x is a singe sample
            prediction = prediction[support]  # Keep only support features
        else:
            prediction = prediction[:, support]  # Keep only support features
        return prediction

    def save(self, filename=None, append=''):
        """
        Saves the model weights to disk (in the run folder if a logger was
        given, otherwise in the current folder)
        :param filename: string representing a file to which save the model
        :param append: string to append to the filename before the extension)
        """
        # Save the DQN weights to disk
        f = ('model%s.h5' % append) if filename is None else filename
        if not f.endswith('.h5'):
            f += '.h5'
        a = 'architecture_' + f.lstrip('.h5') + '.json'
        if self.logger is not None:
            self.logger.log('Saving model as %s' % self.logger.path + f)
            self.model.save_weights(self.logger.path + f)
            with open(self.logger.path + a, 'w') as a_file:
                a_file.write(self.model.to_json())
                a_file.close()
        else:
            self.model.save_weights(f)
            with open(a, 'w') as a_file:
                a_file.write(self.model.to_json())
                a_file.close()

    def save_encoder(self, filename):
        """
        Save the encoder model
        :param filename: filename to which save the model
        """
        self.encoder.save(filename)

    def load(self, filename):
        """
        Loads the full model weights from file
        :param filename: file from which load the weights
        """
        if self.logger is not None:
            self.logger.log('Loading weights from file...')
        self.model.load_weights(filename)

    def set_support(self, support):
        """
        :param support: np.array, boolean mask to use as support 
        """
        self.support = support

    def get_support_dim(self):
        """
        :return: the number of True values in the support 
        """
        if self.support is not None:
            return self.support.sum()
        else:
            return self.get_features_number()

    def get_features_number(self):
        """
        :return: the number of True values in the support 
        """
        if self.use_vae or self.use_dense or self.use_contractive_loss:
            layer = 'features'
        else:
            layer = 'to_flatten'
        return reduce(mul, self.model.get_layer(layer).get_output_at(0).get_shape().as_list()[1:])
