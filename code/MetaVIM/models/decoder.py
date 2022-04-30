import torch
import torch.nn as nn
from torch.nn import functional as F

from utils import helpers as utl

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

'''
function:
----- 1. StateTransitionDecoder
----- 2. RewardDecoder
----- 3. NeighborStateTransitionDecoder (add action of neighbor)
----- 4. NeighborRewardDecoder (add action of neighbor)
----- 5. TaskDecoder
'''


class StateTransitionDecoder(nn.Module):
    def __init__(self,
                 latent_dim,
                 layers,
                 #
                 action_dim,
                 action_embed_dim,
                 state_dim,
                 state_embed_dim,
                 pred_type='deterministic'
                 ):
        super(StateTransitionDecoder, self).__init__()

        self.state_encoder = utl.FeatureExtractor(state_dim, state_embed_dim, F.relu)
        self.action_encoder = utl.FeatureExtractor(action_dim, action_embed_dim, F.relu)

        curr_input_dim = latent_dim + state_embed_dim + action_embed_dim
        self.fc_layers = nn.ModuleList([])
        for i in range(len(layers)):
            self.fc_layers.append(nn.Linear(curr_input_dim, layers[i]))
            curr_input_dim = layers[i]

        # output layer
        if pred_type == 'gaussian':
            self.fc_out = nn.Linear(curr_input_dim, 2 * state_dim)
        else:
            self.fc_out = nn.Linear(curr_input_dim, state_dim)

    def forward(self, latent_state, state, action):

        ha = self.action_encoder(action)
        hs = self.state_encoder(state)

        h = torch.cat((latent_state, hs, ha), dim=-1)

        for i in range(len(self.fc_layers)):
            h = F.relu(self.fc_layers[i](h))

        return self.fc_out(h)


class RewardDecoder(nn.Module):
    def __init__(self,
                 layers,
                 latent_dim,
                 action_dim,
                 action_embed_dim,
                 state_dim,
                 state_embed_dim,
                 num_states,
                 multi_head=False,
                 pred_type='deterministic',
                 input_prev_state=True,
                 input_action=True,
                 ):
        super(RewardDecoder, self).__init__()

        self.pred_type = pred_type
        self.multi_head = multi_head
        self.input_prev_state = input_prev_state
        self.input_action = input_action

        if self.multi_head:
            # one output head per state to predict rewards
            curr_input_dim = latent_dim
            self.fc_layers = nn.ModuleList([])
            for i in range(len(layers)):
                self.fc_layers.append(nn.Linear(curr_input_dim, layers[i]))
                curr_input_dim = layers[i]
            self.fc_out = nn.Linear(curr_input_dim, num_states)
        else:
            # get state as input and predict reward prob
            self.state_encoder = utl.FeatureExtractor(state_dim, state_embed_dim, F.relu)
            self.action_encoder = utl.FeatureExtractor(action_dim, action_embed_dim, F.relu)
            curr_input_dim = latent_dim + state_embed_dim
            if input_prev_state:
                curr_input_dim += state_embed_dim
            if input_action:
                curr_input_dim += action_embed_dim
            self.fc_layers = nn.ModuleList([])
            for i in range(len(layers)):
                self.fc_layers.append(nn.Linear(curr_input_dim, layers[i]))
                curr_input_dim = layers[i]

            if pred_type == 'gaussian':
                self.fc_out = nn.Linear(curr_input_dim, 2)
            else:
                self.fc_out = nn.Linear(curr_input_dim, 1)

    def forward(self, latent_state, next_state, prev_state=None, action=None):

        if self.multi_head:
            h = latent_state.clone()
        if not self.multi_head:
            hns = self.state_encoder(next_state)
            h = torch.cat((latent_state, hns), dim=-1)
            if self.input_action:
                ha = self.action_encoder(action)
                h = torch.cat((h, ha), dim=-1)
            if self.input_prev_state:
                hps = self.state_encoder(prev_state)
                h = torch.cat((h, hps), dim=-1)

        for i in range(len(self.fc_layers)):
            h = F.relu(self.fc_layers[i](h))

        p_x = self.fc_out(h)
        if self.pred_type == 'deterministic' or self.pred_type == 'gaussian':
            pass
        elif self.pred_type == 'bernoulli':
            p_x = torch.sigmoid(p_x)
        elif self.pred_type == 'categorical':
            p_x = torch.softmax(p_x, 1)
        else:
            raise NotImplementedError

        return p_x


class NeighborStateTransitionDecoder(nn.Module):
    def __init__(self,
                 latent_dim,
                 layers,
                 #
                 action_dim,
                 action_embed_dim,
                 state_dim,
                 state_embed_dim,
                 pred_type='deterministic',
                 ):
        super(NeighborStateTransitionDecoder, self).__init__()

        self.state_encoder = utl.FeatureExtractor(state_dim, state_embed_dim, F.relu)
        self.action_encoder = utl.FeatureExtractor(action_dim, action_embed_dim, F.relu)

        curr_input_dim = latent_dim + state_embed_dim + action_embed_dim * 5
        self.fc_layers = nn.ModuleList([])
        for i in range(len(layers)):
            self.fc_layers.append(nn.Linear(curr_input_dim, layers[i]))
            curr_input_dim = layers[i]

        # output layer
        if pred_type == 'gaussian':
            self.fc_out = nn.Linear(curr_input_dim, 2 * state_dim)
        else:
            self.fc_out = nn.Linear(curr_input_dim, state_dim)

    def forward(self, latent_state, state, action, action_neighbor):

        ha = self.action_encoder(action)
        hs = self.state_encoder(state)
        h = torch.cat((latent_state, hs, ha), dim=1)

        for i in range(1, 5):
            ha_neighbor = self.action_encoder(action_neighbor[i])
            h = torch.cat((h, ha_neighbor), dim=1)

        for i in range(len(self.fc_layers)):
            h = F.relu(self.fc_layers[i](h))

        return self.fc_out(h)


class NeighborRewardDecoder(nn.Module):
    def __init__(self,
                 layers,
                 latent_dim,
                 action_dim,
                 action_embed_dim,
                 state_dim,
                 state_embed_dim,
                 num_states,
                 multi_head=False,
                 pred_type='deterministic',
                 input_prev_state=True,
                 input_action=True,
                 input_action_neighbor=True,
                 ):
        super(NeighborRewardDecoder, self).__init__()

        self.pred_type = pred_type
        self.multi_head = multi_head
        self.input_prev_state = input_prev_state
        self.input_action = input_action
        self.input_action_neighbor = input_action_neighbor

        if self.multi_head:
            # one output head per state to predict rewards
            curr_input_dim = latent_dim
            self.fc_layers = nn.ModuleList([])
            for i in range(len(layers)):
                self.fc_layers.append(nn.Linear(curr_input_dim, layers[i]))
                curr_input_dim = layers[i]
            self.fc_out = nn.Linear(curr_input_dim, num_states)
        else:
            # get state as input and predict reward prob
            self.state_encoder = utl.FeatureExtractor(state_dim, state_embed_dim, F.relu)
            self.action_encoder = utl.FeatureExtractor(action_dim, action_embed_dim, F.relu)
            curr_input_dim = latent_dim + state_embed_dim  # current_state
            if input_prev_state:
                curr_input_dim += state_embed_dim  # previous_state
            if input_action:
                curr_input_dim += action_embed_dim
            if input_action_neighbor:
                curr_input_dim += action_embed_dim * 4
            self.fc_layers = nn.ModuleList([])

            for i in range(len(layers)):
                self.fc_layers.append(nn.Linear(curr_input_dim, layers[i]))
                curr_input_dim = layers[i]

            if pred_type == 'gaussian':
                self.fc_out = nn.Linear(curr_input_dim, 2)
            else:
                self.fc_out = nn.Linear(curr_input_dim, 1)

    def forward(self, latent_state, next_state, prev_state=None, action=None, action_neighbor=None):

        if self.multi_head:
            h = latent_state.clone()
        if not self.multi_head:
            hns = self.state_encoder(next_state)
            h = torch.cat((latent_state, hns), dim=-1)
            if self.input_action:
                ha = self.action_encoder(action)
                h = torch.cat((h, ha), dim=-1)
            if self.input_action_neighbor:
                for i in range(1, 5):
                    ha_neighbor = self.action_encoder(action_neighbor[i])
                    h = torch.cat((h, ha_neighbor), dim=-1)
            if self.input_prev_state:
                hps = self.state_encoder(prev_state)
                h = torch.cat((h, hps), dim=-1)

        for i in range(len(self.fc_layers)):
            h = F.relu(self.fc_layers[i](h))

        p_x = self.fc_out(h)
        if self.pred_type == 'deterministic' or self.pred_type == 'gaussian':
            pass
        elif self.pred_type == 'bernoulli':
            p_x = torch.sigmoid(p_x)
        else:
            raise NotImplementedError

        return p_x


class TaskDecoder(nn.Module):
    def __init__(self,
                 layers,
                 latent_dim,
                 pred_type,
                 task_dim,
                 ):
        super(TaskDecoder, self).__init__()

        # "task_description" or "task id"
        self.pred_type = pred_type

        curr_input_dim = latent_dim
        self.fc_layers = nn.ModuleList([])
        for i in range(len(layers)):
            self.fc_layers.append(nn.Linear(curr_input_dim, layers[i]))
            curr_input_dim = layers[i]

        self.fc_out = nn.Linear(curr_input_dim, task_dim)

    def forward(self, latent_state):

        h = latent_state

        for i in range(len(self.fc_layers)):
            h = F.relu(self.fc_layers[i](h))

        y = self.fc_out(h)

        if self.pred_type == 'task_id':
            y = torch.softmax(y, 1)

        return y
