# M1 / SH-01–SH-04: correlación forense entre journals (offline)

**Estado:** incremento ejecutable de M1, NO motor DFIR completo, no sensor y no
verificación de causalidad. Lee únicamente *bundles privados ya verificados*
producidos por `ingest-journal` (exportaciones existentes de `journalctl -o json`).
No contacta sistemas, no instala agentes ni ejecuta comandos externos.

## Trabajo real y enlaces entre componentes

`journal_ingest.verify` verifica cada paquete de entrada contra sus bytes y
recibos. Este módulo conserva las copias exactas de los JSONL y metadatos,
regenera los eventos, vincula cada evento a su archivo y al segmento exacto
`offset/length/SHA-256`, normaliza todos los relojes vía
`forensic_timeline.analyze` y evalúa hipótesis de precedencia entre fuentes.
No hay un `PASS` que certifique una vulnerabilidad o un ataque.

Las relaciones declaradas se clasifican exclusivamente como:

- `TEMPORALLY_FEASIBLE_UNPROVEN`: las cotas de reloj permiten precedencia;
  **no** demuestra relación causal.
- `TEMPORAL_ORDER_INCONCLUSIVE`: los intervalos de reloj se solapan.
- `TEMPORALLY_CONTRADICTED`: el supuesto orden contradice los intervalos;
  también se detectan ciclos del grafo de restricciones y contradicciones
  locales de secuencia.

El expediente se marca
`TEMPORALLY_FEASIBLE_UNVERIFIED`, `INCONCLUSIVE_ORDER` o
`DECLARED_CONSTRAINT_CONTRADICTION`. Las etiquetas de estado no demuestran
identidad del productor, veracidad de reloj, autenticidad ni incidente.

## Formato de hipótesis (obligatorio; 1–128 enlaces)

El ID de cada evento es `sNN-` + `event_id` de `normalized.json` del paquete
correspondiente (con `NN` empezando en `00` y siguiendo el orden de `--bundle`).
Los enlaces deben unir fuentes diferentes.

```json
{
  "schema_version": 1,
  "profile": "cross-source-journal-hypotheses-v1",
  "hypotheses": [
    {
      "from_event_id": "s00-j000001-1234567890abcdef",
      "to_event_id": "s01-j000000-fedcba0987654321"
    }
  ]
}
```

Los IDs del ejemplo son ilustrativos, no se presentan como eventos reales.
Cada journal contiene como máximo 512 entradas y 2 MB; el expediente combina
2–8 fuentes y 512 eventos totales. Sólo acepta objetos JSON tipados estrictos;
rechaza claves duplicadas, fuentes repetidas, enlaces de identidad desconocida,
relaciones consigo mismas, vínculos duplicados y entradas fuera de límites.

## Ejecución y verificación independiente

```bash
python3 -m superhunter ingest-journal --input /privado/lab-a.jsonl \
  --source-id laboratorio-a --clock-uncertainty-ms 1000 \
  --out /privado/source-a
python3 -m superhunter ingest-journal --input /privado/lab-b.jsonl \
  --source-id laboratorio-b --clock-uncertainty-ms 2000 \
  --out /privado/source-b
python3 -m superhunter correlate-journals \
  --bundle /privado/source-a --bundle /privado/source-b \
  --hypotheses /privado/hypotheses.json --out /privado/correlacion-nueva
python3 -m superhunter verify-journal-correlations \
  --bundle /privado/correlacion-nueva
```

Para anclar la salida contra sustituciones posteriores, conservar **fuera del
paquete y antes de la verificación** el SHA-256 de `COMPLETE.json`, y usar
`--expected-complete-sha256 <sha256>` al verificar. Sin un ancla independiente,
un atacante con control total de los bytes y metadatos puede fabricar un
expediente autoconsistente. Un hash nunca autentica al operador ni los relojes.

El verificador lee los originales privados y reconstruye todos los campos del
reporte. Rechaza cambios en datos, offsets, enlaces, resoluciones o afirmaciones
falsas aunque se recalculen los hashes de los archivos derivados.

**Privacidad:** el directorio de salida es 0700 y conserva MESSAGE, cursores y
otros datos sensibles únicamente dentro del paquete privado; no imprimir logs
en stdout ni subir expedientes de casos a GitHub. Los archivos `case.json` y
`REVIEW.md` contienen IDs y hashes, no mensajes privados.

## Próxima unidad de M1 (PENDIENTE)

Correlacionar una segunda familia distinta de evidencia real —por ejemplo
trazas EVM de laboratorio o telemetría de sensores propios—, establecer
identidades independientes y generar hipótesis refutables mediante un
experimento aislado. Este incremento **no** completa SH-01, SH-04 ni M1.
