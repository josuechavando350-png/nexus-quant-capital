# Omega Long-Tail Prioritizer — Census contract

This module orders **research coverage**, not economic execution. It deliberately
does not calculate profit, expected value, capture probability or GO/NO-GO.

Candidates contain four explicit research axes:

- lower market age in blocks is favored (newer market);
- lower market size in USD-WAD is favored (smaller/long-tail market);
- L2 is favored over non-L2 for this discovery lane;
- more route-complexity steps are favored.

No arbitrary scalar weights are used. Ranking uses Pareto dominance: one market
dominates another only when it is at least as favored on every axis and strictly
favored on at least one. Trade-offs stay on the same non-dominated frontier.
Within one frontier, market ID is only a deterministic tie order and does not
claim economic superiority.

Every candidate is evidence-bound. Floats, missing evidence, duplicate markets,
malformed dimensions and authority escalation fail closed.

The output is `research_only`, exposes `economic_score: null`, and never claims
profitability. Signing, broadcasting, spending, phase advancement and Census
closeout are always false.

Component 32 remains partial until this prioritizer is populated from the full
admitted market universe and out-of-sample evidence shows that the lane improves
coverage of economically relevant opportunities without hiding excluded markets.
