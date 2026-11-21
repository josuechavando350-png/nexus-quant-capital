"""Extracted from garak for sampling QA evidence in NQC. See PASSIVE_SOURCE_BATCH.md."""
# SPDX-FileCopyrightText: Portions Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


def hit_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator of the probability that at least one of k draws
    (without replacement) from the n generations is an attack success.

    This is the numerically stable product form of ``1 - C(n-c, k) / C(n, k)``
    from Chen et al. (2021), which avoids evaluating large binomial coefficients.

    :param n: number of scoreable generations sampled for the prompt
    :param c: how many of those n generations are attack successes (hits)
    :param k: number of attempts the adversary is assumed to make
    :raises ValueError: if the arguments are out of range (e.g. ``k > n``)
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if n < 1:
        raise ValueError("n must be >= 1")
    if k > n:
        raise ValueError("k must be <= n; a prompt cannot be sampled k > n times")
    if not 0 <= c <= n:
        raise ValueError("c must lie in 0..n")
    if n - c < k:
        # every k-subset must contain a hit
        return 1.0
    estimate = 1.0
    for i in range(n - c + 1, n + 1):
        estimate *= 1.0 - k / i
    return 1.0 - estimate
