# NQC 666 R6 — entrada de testigos y evaluación de dos optimizaciones

**La integración con estado auténtico no está completada.** El paquete técnico
disponible de NQC031 declara captura incompleta/no autenticada de cadena 4663,
sin pruebas de cuenta/storage ni raíz pretransacción. R5 admite estado Ethereum
al final de bloque. R6 no cambia esas fronteras ni convierte esa captura en prueba.

**Decisión final: conservar baseline/R5.** La confirmación de A+B encontró máximos
peores y un descarte adicional; se rechaza su promoción. Los caminos alternativos
se conservan solo para reproducir la investigación, no como recomendación de uso.

Se implementó una entrada offline de capturas JSON-RPC: correlación de IDs,
lecturas fijadas a hash, cobertura exacta, normalización del ancho de claves de
storage y el verificador/defensas de R5. La captura puede llegar de un recolector
externo autorizado, pero R6 no hace solicitudes. Pruebas y mediciones positivas
usan únicamente el corpus sintético R3. El paquete NQC031 sirve como caso negativo
documental y de rechazo; no se ejecutan sus contratos ni se auditan sus finanzas.

## Rutas y uso

`baseline` usa el verificador R5 después de serializar el paquete normalizado.
`object` evita ese encode/parse repetido y conserva el decoder R5. `optimized`
además usa fromhex + comparación de round-trip para mantener la misma aceptación
de hexadecimal canónico. Las tres rutas tienen las mismas defensas y todos los
checks RLP/Keccak/trie/identidad/vigencia. API y CLI usan **baseline por defecto**.
REPORT/STABILITY indican si alguna alternativa pasó el criterio experimental.

Para emitir las cuatro solicitudes documentales, sin enviarlas:

```sh
python scripts/import_capture.py --policy policy.json --out /tmp/nqc-r6-plan-new
```

Formato de captura: objeto con `schema="nqc666-rpc-capture-v1"`,
`statePoint="end_of_block"`, `requests` exactamente como requests.json y
`responses` como lista de las cuatro respuestas completas JSON-RPC. Se admiten
respuestas desordenadas, no faltantes/duplicadas/con error. No se admite `latest`
ni `pending`, otra cadena o estado pretransacción. Una etiqueta authenticated no
es parte del esquema. Código y pruebas quedan vinculados criptográficamente al
encabezado fijado por la política externa; no se autoextrae la política de la captura.

```sh
python scripts/import_capture.py --policy policy.json --capture capture.json \
  --library /tmp/nqc-r6-run-new/target/release/libnqc_666_stable_ingress.so \
  --library-sha256 HASH_DE_BUILD_METADATA --observed-now TIMESTAMP_DE_REPLAY \
  --variant baseline --out /tmp/nqc-r6-import-new
```

Salida 0: plan emitido o vinculación a la raíz verificada, según `status`;
salida 2: rechazo registrado, sin hechos parciales. Ninguna salida autoriza
operar. `--assumed-price` produce solo escenario condicional. Precio/oráculo
observado y candidatura comercial siguen desconocidos/bloqueados.
Se conservan bytes y hashes de los dos archivos de entrada. El límite es 2 MiB
para captura y 64 KiB para política. El presupuesto de ingreso incluye parseo,
adaptación y verificación; los plazos R4/R5 se mantienen (50 ms/5 ms) y descartan
salidas tardías sin prometer interrumpir el sistema operativo.

## Reproducción

Linux, Python 3.12, Rust 1.90.0 y dependencias R3 ya instaladas: trie 4.0.0,
rlp 5.0.0, eth-hash 0.8.0, pycryptodome 3.24.1. Sin instalaciones nuevas.

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/reproduce.py --out /tmp/nqc-r6-run-new
PYTHONDONTWRITEBYTECODE=1 python scripts/verify_results.py evidence/benchmark
PYTHONDONTWRITEBYTECODE=1 python scripts/verify_confirmation.py evidence/confirmation
sha256sum -c SHA256SUMS
```

La salida debe ser nueva y fuera del repositorio. Recompila biblioteca R4 y
ejecutable R1 sin cambios/offline; ejecuta suites R6/R5/Rust/aislamiento; mide
36.864 ventanas individuales y verifica estadísticas. Datos de entorno,
calibración, cada tiempo bruto y los descartes se conservan sin recortes.
`raw.zip`: vectores u64 little-endian por variante/ronda, índices y calibración;
un byte por estado (0 salida, 1 descarte de plazo/caducidad). Las variantes rotan
la primera posición por grupo; semillas y resultados observables quedan registrados.

La confirmación posterior se reproduce por separado, con la biblioteca compilada
y su SHA256 de build-metadata.json:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/confirmation.py \
  --library /tmp/nqc-r6-run-new/target/release/libnqc_666_stable_ingress.so \
  --library-sha256 HASH_DE_BUILD_METADATA --out /tmp/nqc-r6-confirmation-new
PYTHONDONTWRITEBYTECODE=1 python scripts/verify_confirmation.py /tmp/nqc-r6-confirmation-new
```

Son 98.304 ventanas adicionales. No se agrupan con la matriz inicial para esconder
regresiones. STABILITY.json contiene la decisión final, que prevalece sobre el
resultado provisional favorable a A+B de la primera matriz.

La ventana de ingreso comienza con la captura completa **ya en memoria** y
termina tras el escenario y la puerta de autorización cerrada. No incluye red,
archivo, builder, oráculo/IRM o simulación EVM. No se llama latencia end-to-end
de Ethereum ni se compara directamente contra la ventana más corta publicada en R5.

## Compatibilidad y confianza

La normalización de claves acepta cantidades mínimas o bytes de 1–32 bytes,
en minúsculas, y las lleva a 32 bytes; no acepta todas las representaciones laxas
que algunos clientes puedan emitir. Los demás campos conservan la política
estricta de R5. Un cliente sin bloque fijado por hash no recibe fallback implícito.

Referencias primarias consultadas el 2026-10-19:
- https://eips.ethereum.org/EIPS/eip-1186
- https://eips.ethereum.org/EIPS/eip-1898
- https://ethereum.github.io/execution-apis/api/methods/eth_getProof/

EIP-1898 permite solicitar estado por hash; requireCanonical expresa lo que se
exige al nodo, no prueba consenso por sí mismo. R6 mantiene canonicality unknown.
Los hashes de archivos prueban integridad local, no autenticidad de cadena.

## 5 ns

No hay una nueva demostración <=5 ns. Este cambio afecta JSON y verificación
criptográfica, que se miden en micro/milisegundos. La investigación anterior del
filtro preparado mantiene su alcance y evidencia: una media por operación en lote
no equivale a latencia individual ni incluye la adquisición/verificación de estado.
No se introduce ASM, SIMD, FPGA, nuevos procesos o dependencias sin mejora medida.
