import torch
import torch.nn as nn
from basicts.archs.BasicMTS_arch.MLP import MLP_res

class BasicMTS(nn.Module):
    def __init__(self, **model_args):
        super().__init__()
        # attributes
        print(model_args.keys())
        self.num_nodes  = model_args['num_nodes']
        self.node_dim   = model_args['node_dim']
        self.temp_dim   = model_args['temp_dim']
        self.input_len  = model_args['input_len']
        self.input_dim  = model_args['input_dim']
        self.embed_dim  = model_args['embed_dim']
        self.output_len = model_args['output_len']

        self.if_T_i_D = True
        self.if_D_i_W = True

        # spatial embeddings
        self.node_emb = nn.Parameter(torch.empty(self.num_nodes, self.node_dim))
        nn.init.xavier_normal_(self.node_emb)
        # temporal embeddings
        if self.if_T_i_D:
            self.T_i_D_emb  = nn.Parameter(torch.empty(288, self.temp_dim))
            nn.init.xavier_normal_(self.T_i_D_emb)
        if self.if_D_i_W:
            self.D_i_W_emb  = nn.Parameter(torch.empty(7, self.temp_dim))
            nn.init.xavier_normal_(self.D_i_W_emb)

        # embedding layer 
        self.time_series_emb_layer = nn.Conv2d(in_channels=self.input_dim * self.input_len, out_channels=self.embed_dim, kernel_size=(1, 1), bias=True)
        
        # encoding
        num_layer = 3
        self.hidden_dim = self.embed_dim+self.node_dim+self.temp_dim*(int(self.if_D_i_W) + int(self.if_T_i_D))
        self.encoder = nn.Sequential(*[MLP_res(self.hidden_dim, self.hidden_dim) for _ in range(num_layer)])

        # regression
        self.regression_layer = nn.Conv2d(in_channels=self.hidden_dim, out_channels=self.output_len, kernel_size=(1,1), bias=True)

    def forward(self, history_data: torch.Tensor, **kwargs) -> torch.Tensor:
        """feed forward.

        Args:
            history_data (torch.Tensor): history data with shape [B, L, N, C]

        Returns:
            torch.Tensor: prediction wit shape [B, L, N, C]
        """
        # prepare data
        X = history_data[..., range(self.input_dim)]
        t_i_d_data   = history_data[..., 1]
        d_i_w_data   = history_data[..., 2]

        if self.if_T_i_D:
            T_i_D_emb = self.T_i_D_emb[(t_i_d_data[:, -1, :] * 288).type(torch.LongTensor)]    # [B, N, D]
        else:
            T_i_D_emb = None
        if self.if_D_i_W:
            D_i_W_emb = self.D_i_W_emb[(d_i_w_data[:, -1, :]).type(torch.LongTensor)]          # [B, N, D]
        else:
            D_i_W_emb = None

        # time series embedding
        B, L, N, _ = X.shape
        X = X.transpose(1, 2).contiguous()                      # B, N, L, 1
        X = X.view(B, N, -1).transpose(1, 2).unsqueeze(-1)      # B, D, N, 1
        time_series_emb = self.time_series_emb_layer(X)         # B, D, N, 1

        # expand node embeddings
        node_emb = self.node_emb.unsqueeze(0).expand(B, -1, -1).transpose(1, 2).unsqueeze(-1)  # B, D, N, 1
        # temporal embeddings
        tem_emb  = []
        if T_i_D_emb is not None:
            tem_emb.append(T_i_D_emb.transpose(1, 2).unsqueeze(-1))                     # B, D, N, 1
        if D_i_W_emb is not None:
            tem_emb.append(D_i_W_emb.transpose(1, 2).unsqueeze(-1))                     # B, D, N, 1
        
        # concate all embeddings
        hidden = torch.cat([time_series_emb, node_emb] + tem_emb, dim=1)

        # encoding
        hidden = self.encoder(hidden)

        # regression
        prediction = self.regression_layer(hidden)

        return prediction
