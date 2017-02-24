from deep_ifs.utils.helpers import *
from joblib import Parallel, delayed
from tqdm import tqdm
from sklearn.utils.class_weight import compute_class_weight
import numpy as np
import pandas as pd


def episode(env, policy, video=False):
    frame_counter = 0

    # Get current state
    state = env.reset()
    reward = 0
    done = False

    # Start episode
    ep_output = []
    while not done:
        frame_counter += 1

        # Select and execute the action, get next state and reward
        action = policy.draw_action(state, done)
        next_state, reward, done, info = env.step(action)

        # build SARS' tuple
        ep_output.append([state, action, reward, next_state])

        # Render environment
        if video:
            env.render()

        # Update state
        state = next_state

    return ep_output


def collect_sars(env, policy, episodes=100, n_jobs=-1):
    # Collect episodes in parallel
    dataset = Parallel(n_jobs=n_jobs)(
        delayed(episode)(env, policy) for _ in tqdm(xrange(episodes))
    )
    dataset = np.asarray(flat2list(dataset))  # Each episode is in a list, so the dataset needs to be flattened
    header = ['S', 'A', 'R', 'SS']
    return pd.DataFrame(dataset, columns=header)


def get_class_weights(sars):
    # Takes as input a SARS' dataset in pandas format
    # Returns a dictionary with classes (reward values) as keys and weights as values
    # The return value can be passed directly to Keras's class_weight parameter in model.fit
    classes = sars.R.unique()
    y = sars.R.as_matrix()
    weights = compute_class_weight('balanced', classes, y)
    return dict(zip(classes, weights))


def split_dataset_for_ifs(dataset, features='F', target='R'):
    x = np.array(_ for _ in dataset[features])
    y = np.array(_ for _ in dataset[target])
    return x, y


# TODO split_dataset_for_fqi
def split_dataset_for_fqi(dataset):
    pass


def build_farf(nn, sars):
    # Build FARF' dataset using SARS' dataset:
    # F = NN[0].features(S)
    # A = A
    # R = R
    # F' = NN[0].features(S')
    farf = []
    for datapoint in sars.itertuples():
        f = nn.flat_encode(datapoint.S)
        a = datapoint.A
        r = datapoint.R
        ff = nn.flat_encode(datapoint.SS)
        farf.append([f, a, r, ff])
    farf = np.array(farf)
    header = ['F', 'A', 'R', 'FF']
    return pd.DataFrame(farf, columns=header)


def build_sfadf(nn_stack, nn, support, sars):
    # Build SFADF' dataset using SARS' dataset:
    # S = S
    # F = NN_stack.s_features(S)
    # A = A
    # D = NN[i-1].s_features(S) - NN[i-1].s_features(S')
    # F' = NN_stack.s_features(S')
    sfadf = []
    for datapoint in sars.itertuples():
        s = datapoint.S
        f = nn_stack.s_features(datapoint.S)
        a = datapoint.A
        # TODO Ask Restelli if D are the dynamics of only the selected features
        d = nn.s_features(datapoint.S, support) - nn.s_features(datapoint.SS, support)
        ff = nn_stack.s_features(datapoint.SS)
        sfadf.append([s, f, a, d, ff])
    sfadf = np.array(sfadf)
    header = ['S', 'F', 'A', 'D', 'FF']
    return pd.DataFrame(sfadf, columns=header)


def build_sares(model, sfadf):
    # Build SARes dataset from SFADF':
    # S = S
    # A = A
    # Res = D - M(F)
    sares = []
    for datapoint in sfadf.itertuples():
        s = datapoint.S
        a = datapoint.A
        # TODO Ask Restelli if D - Model(F) is a literal subtraction
        res = datapoint.D - model.predict(datapoint.F)
        sares.append([s, a, res])
    sares = np.array(sares)
    header = ['S', 'A', 'RES']
    return pd.DataFrame(sares, columns=header)


def build_fadf(nn_stack, nn, sars, sfadf):
    # Build new FADF' dataset from SARS' and SFADF':
    # F = NN_stack.s_features(S) + NN[i].features(S)
    # A = A
    # D = SFADF'.D
    # F' = NN_stack.s_features(S') + NN[i].features(S')
    faf = []
    for datapoint in sars.itertuples():
        f = np.append(nn_stack.s_features(datapoint.S), nn.flat_encode(datapoint.S))
        a = datapoint.A
        ff = np.append(nn_stack.s_features(datapoint.SS), nn.flat_encode(datapoint.SS))
        faf.append([f, a, ff])
    faf = np.array(faf)
    header = ['F', 'A', 'FF']
    fadf = pd.DataFrame(faf, columns=header)
    fadf['D'] = sfadf.D
    fadf = fadf[['F', 'A', 'D', 'FF']]
    return fadf


def build_global_farf(nn_stack, sars):
    # Build FARF' dataset using SARS' dataset:
    # F = NN_stack.s_features(S)
    # A = A
    # R = R
    # F' = NN_stack.s_features(S')
    farf = []
    for datapoint in sars.itertuples():
        f = nn_stack.s_features(datapoint.S)
        a = datapoint.A
        r = datapoint.R
        ff = nn_stack.s_features(datapoint.SS)
        farf.append([f, a, r, ff])
    farf = np.array(farf)
    header = ['F', 'A', 'R', 'FF']
    return pd.DataFrame(farf, columns=header)
