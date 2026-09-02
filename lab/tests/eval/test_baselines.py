from __future__ import annotations

import numpy as np

from groove_lab.eval.baselines import MarginalSampler, RetrievalBaseline

STEPS, LANES = 32, 18


def _example(seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    hit = (rng.random((STEPS, LANES)) > 0.94).astype(np.float32)
    return {
        "hit": hit,
        "velocity": (hit * 0.7).astype(np.float32),
        "offset": np.zeros((STEPS, LANES), dtype=np.float32),
        "conditions": rng.random(16).astype(np.float32),
    }


def test_retrieval_returns_a_real_corpus_window() -> None:
    corpus = [_example(index) for index in range(20)]
    baseline = RetrievalBaseline(corpus)
    query = corpus[7]
    observed = np.ones((STEPS, LANES), dtype=np.float32)
    observed[16:, :] = 0.0
    result = baseline.complete(query, observed)
    # Perfect observed match: the nearest neighbour must be the query itself.
    assert np.array_equal(result["hit"], corpus[7]["hit"])


def test_retrieval_cannot_see_the_answer() -> None:
    # The whole comparison is void if the baseline matches on cells the task
    # masked. Two queries identical on the observed half and opposite on the
    # hidden half must retrieve the same neighbour.
    corpus = [_example(index) for index in range(20)]
    baseline = RetrievalBaseline(corpus)
    observed = np.ones((STEPS, LANES), dtype=np.float32)
    observed[16:, :] = 0.0

    query = {key: value.copy() for key, value in corpus[3].items()}
    tampered = {key: value.copy() for key, value in corpus[3].items()}
    tampered["hit"][16:, :] = 1.0 - tampered["hit"][16:, :]

    first = baseline.complete(query, observed)
    second = baseline.complete(tampered, observed)
    assert np.array_equal(first["hit"], second["hit"])


def test_retrieval_never_invents_a_pattern() -> None:
    corpus = [_example(index) for index in range(20)]
    baseline = RetrievalBaseline(corpus)
    observed = np.zeros((STEPS, LANES), dtype=np.float32)
    known = {tuple(np.argwhere(e["hit"] > 0.5).flatten()) for e in corpus}
    for seed in range(5):
        out = baseline.complete(_example(100 + seed), observed)
        assert tuple(np.argwhere(out["hit"] > 0.5).flatten()) in known


def test_marginal_sampler_reproduces_the_corpus_density() -> None:
    corpus = [_example(index) for index in range(200)]
    sampler = MarginalSampler(corpus, seed=0)
    generated = [sampler.sample() for _ in range(200)]
    corpus_density = float(np.stack([e["hit"] for e in corpus]).mean())
    sampled_density = float(np.stack([g["hit"] for g in generated]).mean())
    assert abs(sampled_density - corpus_density) < 0.01


def test_marginal_sampler_is_deterministic_for_a_seed() -> None:
    corpus = [_example(index) for index in range(20)]
    first = MarginalSampler(corpus, seed=3).sample()
    second = MarginalSampler(corpus, seed=3).sample()
    assert np.array_equal(first["hit"], second["hit"])
