"""The step-token masked HVO, with the task embedding specification 12.1 asks for.

The tokenisation is not a free choice here: the CPU spike measured 32 decoding
steps for the step-token layout against 16 for cell-token, and section 19.4 made
step-token the architecture constraint plan 6 inherits.
"""

from __future__ import annotations

import torch
from torch import nn

from ..model import CONDITIONS, D_MODEL, LANES, MAX_SUBHITS, STEPS, _encoder
from .tasks import TASK_ORDER


class MaskedHvo(nn.Module):
    sequence_length = STEPS

    def __init__(self) -> None:
        super().__init__()
        self.value_projection = nn.Linear(LANES * 4, D_MODEL)
        self.step_embedding = nn.Embedding(STEPS, D_MODEL)
        self.task_embedding = nn.Embedding(len(TASK_ORDER), D_MODEL)
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
        task: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        batch = hit.shape[0]
        # Masked cells must carry no information, so the observed mask gates the
        # values rather than merely accompanying them.
        gate = observed_mask
        values = torch.stack(
            (hit * gate, velocity * gate, offset * gate, gate), dim=-1
        )
        embedded = self.value_projection(values.reshape(batch, STEPS, LANES * 4))
        embedded = embedded + self.step_embedding(self.step_index).unsqueeze(0)
        embedded = embedded + self.condition_projection(conditions).unsqueeze(1)
        embedded = embedded + self.task_embedding(task).unsqueeze(1)

        encoded = self.encoder(embedded)
        return {
            "hit_logits": self.hit_head(encoded),
            "subhits_logits": self.subhits_head(encoded).reshape(
                batch, STEPS, LANES, MAX_SUBHITS
            ),
            "velocity": torch.sigmoid(self.velocity_head(encoded)),
            "offset": torch.tanh(self.offset_head(encoded)),
        }
