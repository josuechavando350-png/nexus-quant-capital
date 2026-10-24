"""CLI del Census del dinero.

  python -m census_dinero plan --run-json run.json
  python -m census_dinero collect --chain ethereum --days 30 --out out/ethereum
  python -m census_dinero collect --chain base --start-ts 1790000000 --end-ts 1790259200 --out out/base-01
  python -m census_dinero analyze --out resultados out/*/liquidaciones.jsonl
  python -m census_dinero verificar --out resultados out/*/liquidaciones.jsonl
"""

import argparse
import calendar
import glob
import json
import os
import signal
import sys
import time

from . import verificar
from .analyze import analyze, load, write_outputs
from .collect import Collector

MAX_JOBS = 20      # trabajos simultáneos de Actions en una cuenta gratuita


def parse_utc(text):
    return calendar.timegm(time.strptime(text.replace("Z", ""), "%Y-%m-%dT%H:%M:%S"))


def plan(cfg, now=None):
    """Matriz cadena × tramo con límites por timestamp: todos los trabajos parten la misma ventana."""
    now = time.time() if now is None else now
    days = float(cfg["days"])
    if cfg.get("end_utc"):
        end_ts = parse_utc(cfg["end_utc"])
    else:
        end_ts = int(now // 3600) * 3600 - 3600       # hora cerrada, una hora atrás: ya finalizada
    start_ts = end_ts - int(round(days * 86400))
    tramos = cfg.get("tramos", 1)
    include = []
    for chain in cfg["chains"]:
        n = int(tramos.get(chain, 1) if isinstance(tramos, dict) else tramos)
        n = max(1, n)
        for k in range(n):
            a = start_ts + round(k * (end_ts - start_ts) / n)
            b = start_ts + round((k + 1) * (end_ts - start_ts) / n)
            include.append({"chain": chain, "tramo": k + 1, "tramos": n, "start_ts": a, "end_ts": b,
                            "label": f"{chain}-{k + 1:02d}de{n:02d}"})
    if cfg.get("solo"):
        # Reanudar: solo los tramos indicados; el reporte toma el resto de `incluir_corridas`.
        include = [r for r in include if r["label"] in set(cfg["solo"])]
    if len(include) > 256:
        raise SystemExit(f"demasiados tramos: {len(include)} (máximo 256)")
    return {"include": include}, {"start_ts": start_ts, "end_ts": end_ts, "days": days, "jobs": len(include)}


def tranche_files(res_root, run_ids):
    """liquidaciones.jsonl por tramo: de cada etiqueta se toma la primera corrida (en el orden dado)
    donde el tramo terminó sin falla; si ninguna terminó bien, la primera que lo tenga."""
    best = {}
    for rid in run_ids:
        for p in sorted(glob.glob(os.path.join(res_root, "corridas", str(rid), "*", "*", "liquidaciones.jsonl"))):
            label = os.path.basename(os.path.dirname(p))
            ok = False
            meta = os.path.join(os.path.dirname(p), "meta.json")
            if os.path.exists(meta):
                with open(meta) as fh:
                    m = json.load(fh)
                ok = not m.get("fatal_error") and not m.get("interrupted")
            if label not in best or (ok and not best[label][1]):
                best[label] = (p, ok)
    return [p for p, _ in best.values()]


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    ap = argparse.ArgumentParser(prog="census_dinero")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="matriz de tramos para el workflow (salida para GITHUB_OUTPUT)")
    p.add_argument("--run-json", required=True)

    c = sub.add_parser("collect", help="recolecta y enriquece liquidaciones de una cadena")
    c.add_argument("--chain", required=True, choices=["ethereum", "base", "arbitrum"])
    c.add_argument("--days", type=float, default=30)
    c.add_argument("--start-ts", type=int)
    c.add_argument("--end-ts", type=int)
    c.add_argument("--tramo", help="etiqueta del tramo, p. ej. base-03de10")
    c.add_argument("--out", required=True)
    c.add_argument("--protocols", default="aave,morpho")
    c.add_argument("--workers", type=int, default=8)
    c.add_argument("--rps", type=float, default=10)
    c.add_argument("--time-budget-min", type=float, default=300)
    c.add_argument("--end-block", type=int)

    a = sub.add_parser("analyze", help="agrega resultados y escribe el reporte")
    a.add_argument("--out", required=True)
    a.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a.add_argument("--run-json", help="run.json de la corrida, para saber qué tramos se esperaban")
    a.add_argument("inputs", nargs="+")

    f = sub.add_parser("archivos", help="lista los tramos a juntar (corrida actual + incluir_corridas)")
    f.add_argument("--res", required=True, help="clon de la rama de resultados")
    f.add_argument("--run", required=True)
    f.add_argument("--run-json", required=True)

    v = sub.add_parser("verificar", help="compara una muestra de filas contra el explorador")
    v.add_argument("--out", required=True)
    v.add_argument("--per-chain", type=int, default=4)
    v.add_argument("inputs", nargs="+")

    args = ap.parse_args(argv)
    if args.cmd == "plan":
        with open(args.run_json) as fh:
            cfg = json.load(fh)
        if cfg.get("modo") == "verificar":
            # Solo verificar una corrida anterior: la matriz queda con un tramo simbólico que no corre.
            print("modo=verificar")
            print(f"fuente={int(cfg['corrida'])}")
            print('matrix={"include":[{"chain":"ninguna","label":"sin-recoleccion"}]}')
            return 0
        print("modo=recolectar")
        matrix, info = plan(cfg)
        if info["jobs"] > MAX_JOBS:
            print(f"aviso: {info['jobs']} trabajos; más de {MAX_JOBS} esperarán turno", file=sys.stderr)
        print("matrix=" + json.dumps(matrix, separators=(",", ":")))
        print("window=" + json.dumps(info, separators=(",", ":")))
        return 0
    if args.cmd == "collect":
        signal.signal(signal.SIGTERM, _interrupt)
        col = Collector(args.chain, protocols=[p.strip() for p in args.protocols.split(",") if p.strip()],
                        workers=args.workers, rps=args.rps, time_budget_s=args.time_budget_min * 60)
        tramo = None
        if args.tramo:
            tramo = {"label": args.tramo, "start_ts": args.start_ts, "end_ts": args.end_ts}
        meta = col.run(args.days, args.out, end_block=args.end_block, start_ts=args.start_ts,
                       end_ts=args.end_ts, tramo=tramo)
        sys.stdout.flush()
        sys.stderr.flush()
        # Sin esperar a hilos de red que ya no importan: lo recolectado ya está escrito.
        os._exit(130 if meta.get("interrupted") else 1 if meta.get("fatal_error") else 0)
    if args.cmd == "archivos":
        with open(args.run_json) as fh:
            cfg = json.load(fh)
        runs = [args.run] + [str(r) for r in cfg.get("incluir_corridas", [])]
        print("\n".join(tranche_files(args.res, runs)))
        return 0
    if args.cmd == "verificar":
        recs, _ = load(args.inputs)
        evidence = []
        for p_ in args.inputs:
            ev_path = os.path.join(os.path.dirname(p_), "evidencia.json")
            if os.path.exists(ev_path):
                with open(ev_path) as fh:
                    evidence += json.load(fh)
        print(verificar.write(verificar.verify(recs, per_chain=args.per_chain, evidence=evidence), args.out))
        return 0
    recs, metas = load(args.inputs)
    expected = None
    if args.run_json:
        with open(args.run_json) as fh:
            expected = json.load(fh)
    res = analyze(recs, metas, expected=expected)
    md = write_outputs(res, recs, args.out, args.date)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
