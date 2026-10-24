# Captura pública histórica Aave

Cuatro lecturas de solo consulta con el build limpio `cc4abee3fb4bc2438057e5bbcfd35145f7ebc1f1`:

- `run-001`: un bloque previo al primer evento, prueba inicial.
- `history-000` a `history-002`: 16 bloques previos a cada evento original.

Las configuraciones y planes se conservan dentro de cada ejecución. Los endpoints
públicos proceden de [PublicNode](https://ethereum.publicnode.com/) y
[dRPC](https://drpc.org/docs/ethereum-api):
`https://ethereum-rpc.publicnode.com` y `https://eth.drpc.org/`.
No se usaron claves, cuentas nuevas ni suscripciones. La existencia de dos URLs
no demuestra independencia de operadores.

`capture.py` conserva stdout/stderr, hashes y estados de salida, con timeout
acotado. Su estado `returned_report_requires_offline_audit` significa únicamente
que obtuvo un informe; no se reescribe después de auditarlo.

La auditoría separada `audit.py` está aplicada en
`../aave-state-audit-20261023/public-read-audit.json`. Para repetirla con el mismo
ejecutable de captura:

```bash
python3 evidence/aave-state-public-attempt-20261023/audit.py \
  --binary /ruta/al/ejecutable-original \
  --output /ruta/nueva/auditoria.json
```

Usa el entorno Python de investigación con Polars. No requiere RPC. La
reproducción byte por byte exige la misma identidad del ejecutable, porque los
exports la incluyen. El bundle de la auditoría conserva el commit original.
No se promete reproducción binaria hermética del compilador y sus dependencias.

Los informes describen cierres de bloque, sin estado intra-bloque ni prueba
criptográfica. La salud no equivale a elegibilidad ejecutable. Los 48 estados
distintos enriquecen los tres eventos existentes; la prueba de un bloque se
solapa con el primer intervalo. No se acredita beneficio ni operación productiva.
