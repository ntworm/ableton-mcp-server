"""Two tokenisations of the same masked HVO grid, at the spec's small tier.

The grid is 32 steps by 18 lanes, matching ``groove.hvo.v3``.  Both variants read
the same five inputs and produce the same four heads.  They differ only in what a
transformer token is, which is the single decision that drives inference cost:

* :class:`CellTokenHvo` gives every ``(step, lane)`` cell its own token, so the
  sequence is 576 long and self-attention is quadratic in that;
* :class:`StepTokenHvo` gives every step one token with the lanes folded into the
  channel dimension, so the sequence is 32 long.

Both carry a ``subhits`` head, because section 11.2 of the design makes the
multiplicity channel mandatory: no dense one-hit-per-cell grid represents the
corpus without loss.
"""

from __future__ import annotations

import torch
from torch import nn

STEPS = 32
LANES = 18
CONDITIONS = 16
MAX_SUBHITS = 4

D_MODEL = 256
LAYERS = 6
HEADS = 8
FFN = 1024


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


def _encoder() -> nn.TransformerEncoder:
    layer = nn.TransformerEncoderLayer(
        d_model=D_MODEL,
        nhead=HEADS,
        dim_feedforward=FFN,
        dropout=0.0,
        batch_first=True,
        norm_first=True,
    )
    return nn.TransformerEncoder(layer, num_layers=LAYERS, enable_nested_tensor=False)


class CellTokenHvo(nn.Module):
    """One token per (step, lane) cell. Sequence length 576."""

    sequence_length = STEPS * LANES

    def __init__(self) -> None:
        super().__init__()
        self.value_projection = nn.Linear(4, D_MODEL)
        self.step_embedding = nn.Embedding(STEPS, D_MODEL)
        self.lane_embedding = nn.Embedding(LANES, D_MODEL)
        self.condition_projection = nn.Linear(CONDITIONS, D_MODEL)
        self.encoder = _encoder()
        self.hit_head = nn.Linear(D_MODEL, 1)
        self.subhits_head = nn.Linear(D_MODEL, MAX_SUBHITS)
        self.velocity_head = nn.Linear(D_MODEL, 1)
        self.offset_head = nn.Linear(D_MODEL, 1)

        steps = torch.arange(STEPS).unsqueeze(1).expand(STEPS, LANES).reshape(-1)
        lanes = torch.arange(LANES).unsqueeze(0).expand(STEPS, LANES).reshape(-1)
        self.register_buffer("step_index", steps, persistent=False)
        self.register_buffer("lane_index", lanes, persistent=False)

    def forward(
        self,
        hit: torch.Tensor,
        velocity: torch.Tensor,
        offset: torch.Tensor,
        observed_mask: torch.Tensor,
        conditions: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        batch = hit.shape[0]
        values = torch.stack((hit, velocity, offset, observed_mask), dim=-1)
        tokens = values.reshape(batch, STEPS * LANES, 4)
        embedded = self.value_projection(tokens)
        embedded = embedded + self.step_embedding(self.step_index).unsqueeze(0)
        embedded = embedded + self.lane_embedding(self.lane_index).unsqueeze(0)
        embedded = embedded + self.condition_projection(conditions).unsqueeze(1)

        encoded = self.encoder(embedded)
        grid = encoded.reshape(batch, STEPS, LANES, D_MODEL)
        return {
            "hit_logits": self.hit_head(grid).squeeze(-1),
            "subhits_logits": self.subhits_head(grid),
            "velocity": torch.sigmoid(self.velocity_head(grid).squeeze(-1)),
            "offset": torch.tanh(self.offset_head(grid).squeeze(-1)),
        }


class StepTokenHvo(nn.Module):
    """One token per step, lanes folded into channels. Sequence length 32."""

    sequence_length = STEPS

    def __init__(self) -> None:
        super().__init__()
        self.value_projection = nn.Linear(LANES * 4, D_MODEL)
        self.step_embedding = nn.Embedding(STEPS, D_MODEL)
        self.condition_projection = nn.Linear(CONDITIONS, D_MODEL)
        self.encoder = _encoder()
        self.hit_head = nn.Linear(D_MODEL, LANES)
        self.subhits_head = nn.Linear(D_MODEL, LANES * MAX_SUBHITS)
        self.velocity_head = nn.Linear(D_MODEL, LANES)
        self.offset_head = nn.Linear(D_MODEL, LANES)

        self.register_buffer("step_index", torch.arange(STEPS), persistent=False)

    def forward(
        self,
        hit: torch.Tensor,
        velocity: torch.Tensor,
        offset: torch.Tensor,
        observed_mask: torch.Tensor,
        conditions: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        batch = hit.shape[0]
        values = torch.stack((hit, velocity, offset, observed_mask), dim=-1)
        tokens = values.reshape(batch, STEPS, LANES * 4)
        embedded = self.value_projection(tokens)
        embedded = embedded + self.step_embedding(self.step_index).unsqueeze(0)
        embedded = embedded + self.condition_projection(conditions).unsqueeze(1)

        encoded = self.encoder(embedded)
        return {
            "hit_logits": self.hit_head(encoded),
            "subhits_logits": self.subhits_head(encoded).reshape(
                batch, STEPS, LANES, MAX_SUBHITS
            ),
            "velocity": torch.sigmoid(self.velocity_head(encoded)),
            "offset": torch.tanh(self.offset_head(encoded)),
        }
