# NQC666 R1 — matemáticas Morpho y adaptador local

Continuación aislada del commit NQC666
`32eb50117bbb398b98b890a63dc28213b6c36c15`. El código y la evidencia de ese corte
permanecen byte-idénticos. Este subpaquete añade aritmética de protocolo; no convierte
fixtures en datos autenticados ni habilita operaciones comerciales.

- [Informe de resultados y límites](REPORT.md)
- [Fuentes recuperadas y hashes](reference/PROVENANCE.json)
- [Resultados de paridad](evidence/differential/results.json)
- [Mediciones agregadas](evidence/summary.json)
- [Manifiesto SHA-256](MANIFEST.sha256)

## Qué implementa

`uint.rs`: enteros U256 de cuatro limbs, suma/resta/producto comprobados y división
general. Variante rápida con operaciones nativas cuando caben, división por un
limb y división exacta por `10^36` mediante dos divisiones por `10^18`.

`math.rs`: conversión de shares a deuda con redondeo hacia arriba, valor de
colateral y LLTV con redondeos hacia abajo, comparación de elegibilidad y Taylor
de intereses de tres términos. Proyección del mercado y fee shares a partir de
una tasa explícitamente suministrada. `Rate::Unknown` produce desconocido;
`ZeroIrm` es una afirmación explícita distinta de una tasa ausente.

`adapter.rs`: liga el fixture a una clave/cadena/bloque/hash, exige timestamp de
accrual coherente, vigencia del dato de oráculo y tamaños representables. Un fallo
envía `Unknown` al motor y elimina la candidatura anterior. No basta con devolver
un error dejando vivo un ticket antiguo. El motor vuelve a comprobar las finanzas
al finalizar y mantiene `commercial_admission=false`.

## Verificar y reproducir

Linux x86_64 en la medición original; Rust 1.90.0 y Python 3.12. No hay dependencias
Rust externas: sólo la dependencia local al motor NQC666 anterior.

```sh
cd migration/experiments/nqc-666/r1-morpho
sha256sum -c MANIFEST.sha256
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify.py
CARGO_TARGET_DIR=/tmp/nqc666-r1-tests cargo test --locked --offline
```

El verificador comprueba las 3,6 millones de muestras de la serie final, sus
controles de reloj, percentiles, hashes de corpus y coincidencia de fuentes.
La serie preliminar completa está en `evidence/initial-harness.zip`, con su
snapshot de código, datos crudos y logs. Su recálculo también quedó verificado
en `evidence/initial-verification.json`; no se mezcla con la tabla final.

Para repetir la comprobación EVM y los benchmarks, prepare fuera del repositorio
un entorno Python aislado con las versiones de `evidence/evm-requirements.txt`.
Son herramientas de validación; no forman parte del motor Rust. La versión de
py-evm utilizada es 0.12.1b1. Instalar estas herramientas requiere descargas;
el comando de reproducción posterior funciona sin red.

El compilador Solidity es 0.8.19, SHA-256:
`7a5c1d3dc9a8eba62bb2ec37192c9178ae5fe8a54a56e5573fd3c9c17cd9eb48`.
Procedencia: [binario oficial solc-bin](https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/solc-linux-amd64-v0.8.19+commit.7dd6d404).
El script rechaza otro hash.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/reproduce.py \
  --out /tmp/nqc666-r1-run \
  --solc /ruta/solc-0.8.19 \
  --evm-python /ruta/evm-venv/bin/python
```

Use un directorio de salida nuevo, fuera del repositorio. El script compila,
ejecuta pruebas, compara 30.006 casos con Python y la referencia Rust, ejecuta
1.179 casos de fórmulas en la EVM local y mide las dos variantes intercaladas.
No ejecuta RPC, firmas, transacciones, despliegues, financiación o envíos públicos.
`execute_bytecode` recibe directamente bytecode y calldata del harness puro.

Desde la raíz de NQC, compruebe además:

```sh
python3 migration/verify_isolation.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s migration -p test_isolation.py
```
