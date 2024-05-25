import gymnasium as gym
from tianshou.data import Collector, VectorReplayBuffer
from tianshou.env import SubprocVectorEnv, DummyVectorEnv
from tianshou.policy import PPOPolicy
from tianshou.trainer import OnpolicyTrainer
from tianshou.utils.net.common import ActorCritic, Net
from tianshou.utils.net.continuous import Actor, Critic
from tianshou.utils import TensorboardLogger
from torch.utils.tensorboard import SummaryWriter
import torch
import random
import numpy as np
import os
import shutil
from pathlib import Path
from option_hedging.gym_envs import make_env
from typing import Dict, Tuple

log_dir = os.path.join(Path(os.path.abspath(__file__)).parent.parent.parent.absolute(), '.logs')
if os.path.exists(log_dir):
    shutil.rmtree(log_dir)
os.makedirs(log_dir, exist_ok=True)
logger = TensorboardLogger(SummaryWriter(log_dir=log_dir), train_interval=256)

seed_value = 123
random.seed(seed_value)
np.random.seed(seed_value)
torch.manual_seed(seed_value)
torch.cuda.manual_seed(seed_value)
torch.cuda.manual_seed_all(seed_value)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False


device = 'cuda' if torch.cuda.is_available() else 'cpu'


def ppo_trial(trainer_kwargs: Dict[str, int],
              epsilon: float,
              sigma: float,
              rho: float,
              action_bins: int,
              duration_bounds: Tuple[int, int],
              buffer_size: int,
              lr: float,
              subproc: bool = False,
              net_arch: Tuple[int] = (64, 32, 16, 4),
              dist_std: float = 0.2
              ):

    env = gym.make('OptionHedgingEnv', epsilon=0)
    if subproc:
        train_envs = SubprocVectorEnv([make_env(epsilon=epsilon,
                                                sigma=sigma,
                                                rho=rho,
                                                action_bins=action_bins,
                                                duration_bounds=duration_bounds,
                                                seed=k) for k in range(20)])
        test_envs = SubprocVectorEnv([make_env(epsilon=epsilon,
                                               sigma=sigma,
                                               rho=0.,
                                               action_bins=action_bins,
                                               duration_bounds=duration_bounds,
                                               seed=k * 50) for k in range(10)])
    else:
        train_envs = DummyVectorEnv([make_env(epsilon=epsilon,
                                              sigma=sigma,
                                              rho=rho,
                                              action_bins=action_bins,
                                              duration_bounds=duration_bounds,
                                              seed=k) for k in range(20)])
        test_envs = DummyVectorEnv([make_env(epsilon=epsilon,
                                             sigma=sigma,
                                             rho=0.,
                                             action_bins=action_bins,
                                             duration_bounds=duration_bounds,
                                             seed=k * 50) for k in range(10)])
    net = Net(state_shape=env.observation_space.shape, hidden_sizes=net_arch, device=device)
    actor = Actor(preprocess_net=net, action_shape=env.action_space.shape, device=device).to(device)
    critic = Critic(preprocess_net=net, device=device).to(device)
    actor_critic = ActorCritic(actor, critic)
    optim = torch.optim.Adam(actor_critic.parameters(), lr=lr)

    def dist_fn(mean):
        return torch.distributions.Normal(mean, dist_std)
    policy = PPOPolicy(
        actor=actor,
        critic=critic,
        optim=optim,
        dist_fn=dist_fn,
        action_space=env.action_space,
        action_scaling=False
    )

    train_collector = Collector(policy, train_envs, VectorReplayBuffer(buffer_size, len(train_envs)))
    test_collector = Collector(policy, test_envs)
    return OnpolicyTrainer(policy=policy,
                           train_collector=train_collector,
                           test_collector=test_collector,
                           logger=logger,
                           **trainer_kwargs
                           )
