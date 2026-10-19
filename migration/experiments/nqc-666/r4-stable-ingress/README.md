# NQC666 R4 — ingreso estable con Rust integrado

Integra localmente las pruebas R3 con las fórmulas R1 mediante una biblioteca Rust,
sin worker de proceso en el camino R4. Refuerza tickets, caducidad y rechazo de
resultados tardíos. No habilita trading ni afirma haber incorporado un testigo real.

- [Diseño, correcciones y límites](DESIGN.md)
- [Resultados](REPORT.md) y [todas las distribuciones](RESULTS.md)
- [Contrato de medición](PRE_REGISTER.md)
- [Procedencia](PROVENANCE.json) y [manifiesto](MANIFEST.sha256)

## Reproducir offline

Linux x86-64, Rust 1.90.0 en PATH y Python 3.12 con las dependencias ya fijadas en
`../r3-state-evidence/requirements.lock`. El wrapper Rust no añade crates externos.
Los scripts no descargan dependencias, no acceden a RPC y no activan workflows.

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/reproduce.py --out /tmp/nqc666-r4-run
```

La salida debe ser nueva y estar fuera del repositorio. Se ejecutan formato, Clippy,
tests Rust nuevos/base/R1, tests Python nuevos/R3, reproducción acotada de fallos,
paridad del ABI, aislamiento y 24 corridas de benchmark. Los binarios se construyen
localmente; se conservan hashes y desensamblado en la evidencia entregada.

Para verificar los percentiles y hashes entregados sin repetir todas las mediciones:

```sh
sha256sum -c MANIFEST.sha256
PYTHONDONTWRITEBYTECODE=1 python scripts/verify.py
PYTHONDONTWRITEBYTECODE=1 python scripts/verify_paired.py
```

La comprobación emparejada adicional tiene su propio comando y preregistro en
[PAIRED_RESULTS.md](PAIRED_RESULTS.md) y [PAIRED_ADDENDUM.md](PAIRED_ADDENDUM.md).
No reemplaza la matriz principal ni está incluida tácitamente en `reproduce.py`.

## Incorporar un paquete externo

El paquete debe cumplir el esquema estricto R3 (`schema`, `chainId`, `blockHash`,
`statePoint=end_of_block`, `header`, `account` EIP-1186 y `code`). La política separada
contiene el ancla, cuenta, código, mercado, prestatario, vigencia y layout esperado;
su formato se puede consultar en `../r3-state-evidence/fixtures/synthetic-index.json`,
pero las políticas de esos fixtures son exclusivamente sintéticas.

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/import_witness.py \
  --packet /ruta/paquete.json \
  --policy /ruta/politica-independiente.json \
  --library /tmp/nqc666-r4-run/target/release/libnqc_666_stable_ingress.so \
  --library-sha256 HASH_DEL_BINARIO_REVISADO \
  --observed-now TIMESTAMP_DE_OBSERVACION \
  --out /tmp/nqc666-importacion-nueva
```

`--assumed-price ENTERO` añade un escenario explícitamente condicional; si falta
acumulación de intereses, se rechaza. El comando es un replay offline, conserva los
dos archivos originales y nunca autoriza una operación. Devuelve código 0 para
pertenencia a raíz verificada y 2 para un rechazo registrado. Los errores de invocación
o de sistema de archivos también terminan sin autorización; no se sobrescribe una
importación anterior.

Para uso local desde Python, importe `NativeMath` y `StableGateway` desde `python/`.
Construya la biblioteca desde fuentes revisadas y fije su hash fuera del paquete.
La política externa no se obtiene automáticamente de datos no confiables. Un resultado
verificado respecto de una raíz todavía necesita consenso, validación de runtime/layout,
oráculo/IRM y autorización financiera antes de cualquier integración comercial.
