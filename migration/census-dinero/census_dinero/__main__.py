"""CLI del Census del dinero.

  python -m census_dinero collect --chain ethereum --days 30 --out out/ethereum
  python -m census_dinero analyze --out resultados out/*/liquidaciones.jsonl
"""

import argparse
import sys
import time

from .analyze import analyze, load, write_outputs
from .collect import Collector


def main(argv=None):
    ap = argparse.ArgumentParser(prog="census_dinero")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="recolecta y enriquece liquidaciones de una cadena")
    c.add_argument("--chain", required=True, choices=["ethereum", "base", "arbitrum"])
    c.add_argument("--days", type=float, default=30)
    c.add_argument("--out", required=True)
    c.add_argument("--protocols", default="aave,morpho")
    c.add_argument("--workers", type=int, default=6)
    c.add_argument("--rps", type=float, default=12)
    c.add_argument("--time-budget-min", type=float, default=300)
    c.add_argument("--end-block", type=int)

    a = sub.add_parser("analyze", help="agrega resultados y escribe el reporte")
    a.add_argument("--out", required=True)
    a.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a.add_argument("inputs", nargs="+")

    args = ap.parse_args(argv)
    if args.cmd == "collect":
        col = Collector(args.chain, protocols=[p.strip() for p in args.protocols.split(",") if p.strip()],
                        workers=args.workers, rps=args.rps, time_budget_s=args.time_budget_min * 60)
        col.run(args.days, args.out, end_block=args.end_block)
        return 0
    recs, metas = load(args.inputs)
    res = analyze(recs, metas)
    md = write_outputs(res, recs, args.out, args.date)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
