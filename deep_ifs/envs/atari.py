import gym
import numpy as np
from gym.utils import seeding
from PIL import Image


class Atari(gym.Env):
    """
    The Atari environment.

    """
    metadata = {
        'render.modes': ['human', 'rgb_array'],
        'video.frames_per_second': 15
    }

    def __init__(self, name='PongDeterministic-v3', clip_reward=False):
        self.IMG_SIZE = (84, 110)
        self.state_shape = (4, 110, 84)
        self.gamma = 0.99

        self.env = gym.make(name)
        self.action_space = self.env.action_space
        self.action_space.values = range(self.action_space.n)
        self.observation_space = self.env.observation_space

        self.clip_reward = clip_reward
        self.final_reward = -1.0 / (1.0 - self.gamma)
        if self.clip_reward:
            self.final_reward = np.clip(self.final_reward)

        # initialize state
        self.seed()
        self.reset()

    def reset(self, state=None):
        state = self._preprocess_observation(self.env.reset())
        self.env.state = np.array([state, state, state, state])
        return self.get_state()

    def step(self, action):
        current_state = self.get_state()
        obs, reward, done, info = self.env.step(int(action))
        # Negative reward at end of episode
        if done:
            reward = self.final_reward
        if self.clip_reward:
            reward = np.clip(reward, -1, 1)

        obs = self._preprocess_observation(obs)
        self.env.state = self._get_next_state(current_state, obs)

        return self.get_state(), reward, done, info

    def get_state(self):
        return self.env.state

    def _preprocess_observation(self, obs):
        image = Image.fromarray(obs, 'RGB').convert('L').resize(self.IMG_SIZE)
        return np.asarray(image.getdata(), dtype=np.uint8).reshape(image.size[1],
                                                                   image.size[0])  # Convert to array and return

    def _get_next_state(self, current, obs):
        # Next state is composed by the last 3 images of the previous state and the new observation
        return np.append(current[1:], [obs], axis=0)

    def render(self, mode='human', close=False):
        self.env.render(mode=mode, close=close)
