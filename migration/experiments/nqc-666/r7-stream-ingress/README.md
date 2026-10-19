# NQC 666 R7 — recepción fragmentada con R5

Integración experimental offline. **R5 permanece predeterminado y sin cambios**;
R7 añade una frontera de recepción opcional alrededor de R6. No contiene cliente
RPC/HTTP, firma, envío a builder ni autorización comercial. No es una integración
autenticada de Morpho ni una certificación del bot completo.

## Estado y arquitectura

`python/stream_ingress.py` mantiene una captura y un buffer por instancia, en el
hilo propietario. `begin(policy, now_s, first_chunk)` revoca inmediatamente el
resultado anterior. Devuelve un objeto de identidad local para `feed(handle,
offset, chunk, now_s)`. Cada offset debe coincidir con los bytes acumulados; no
se aceptan huecos, duplicados, buffers mutables ni fragmentos vacíos.

`finish(handle, now_s)` convierte el buffer en bytes, calcula su SHA256 y llama
al verificador R5 mediante **verify_wire_baseline** de R6. No reutiliza la variante
optimizada que R6 rechazó. Devuelve un recibo de identidad local solamente si
todas las comprobaciones terminan a tiempo. `facts`, `scenario` y `authorize`
aceptan exclusivamente ese mismo objeto, en el mismo hilo y generación.

La verificación conserva encabezado/hash, cadena/punto de estado, cuenta,
runtime/codeHash, nueve slots y semántica del mercado. `scenario` sigue siendo
condicional a un precio supuesto y exige que la deuda almacenada corresponda al
tiempo del bloque. `authorize` siempre devuelve false y las condiciones externas
pendientes. No hay dato autenticado de precio ni operación comercial.

Límites: 2 MiB, 1024 fragmentos, 50 ms por captura, 5 ms por escenario. La cuenta
de 50 ms empieza tras la revocación inicial y al inicializar el buffer; no se
reinicia en cada fragmento. Se incluye ensamblaje, copia final, digest y pruebas.
La caducidad se fija al comienzo; no se extiende por llegar al verificador más
tarde. Los plazos descartan resultados al recuperar el control; no interrumpen
el SO/Python. Sin tráfico, la instancia retiene como máximo el buffer acotado y
ningún resultado anterior es utilizable. Un integrador puede llamar `abort()`.

No se añade concurrencia, red, dependencia, servicio ni proceso residente.
Los 18 roles de NQC siguen siendo responsabilidades lógicas: R7 concierne al
estado/coordinación y a integridad/consistencia. No cambia financiación ni auditoría.

## Reproducir

Desde esta carpeta, con Python 3.12.14, Rust 1.90.0, Cargo y las dependencias
exactas de `../r3-state-evidence/requirements.lock` ya instaladas:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/reproduce.py --out /ruta/fuera-del-repo/r7-run
```

La salida debe ser nueva. El script compila R4/R1 sin red, ejecuta pruebas Rust,
R7, regresiones R6/R5 y aislamiento, y mide las dos rutas. Usa CPU permitida menor,
GC habilitado, CLOCK_MONOTONIC_RAW. No instala paquetes ni modifica el entorno
del sistema. `build-metadata.json` y `benchmark/result.json` identifican herramientas,
CPU, condiciones, inputs y fuentes. Se conservan todas las muestras en `raw.zip`.

Verificar la evidencia publicada sin volver a medir:

```bash
sha256sum --check SHA256SUMS
PYTHONDONTWRITEBYTECODE=1 python scripts/verify_results.py evidence/benchmark
```

El verificador reconstruye percentiles, sumas de fases, semillas/orden, descartes
y hashes de salidas. Estas últimas se comparan con aritmética entera Python
independiente del binario Rust para las 208 combinaciones del corpus sintético.
No basta comparar dos hashes suministrados por el benchmark.

## Reproducir una captura local

Formato de captura/política: los de R6, descritos en
`../r6-witness-ingress/WITNESS_REQUIREMENTS.md`. No se admite una etiqueta
`authenticated=true` como prueba. Ejemplo con archivos proporcionados externamente:

```bash
python scripts/replay_capture.py \
  --policy /ruta/policy.json --capture /ruta/capture.json \
  --library /ruta/r7-run/target/release/libnqc_666_stable_ingress.so \
  --library-sha256 HASH_SHA256_VERIFICADO \
  --observed-now TIEMPO_DE_OBSERVACION \
  --chunk-bytes 4096 --out /ruta/fuera-del-repo/importacion-nueva
```

No copia esos marcadores literalmente: se usan rutas, hash y tiempo del artefacto.
El binario debe provenir de la compilación revisada; un hash solo fija identidad,
no confiabilidad. `--assumed-price` es opcional y siempre produce un escenario
condicional. El tiempo histórico suministrado no convierte un replay en dato vivo.
Los bytes originales de política y captura se conservan. Código de salida 0
significa vínculo relativo con la raíz configurada, **no consenso autenticado**;
2 significa rechazo. El archivo de resultado explicita desconocidos y admisión false.

## Alcance de medición

La ventana comienza antes de `begin`/reset y termina tras la autorización cerrada:
incluye ensamblaje, validaciones, prueba, cálculo Rust e instrumentación. Los
fragmentos ya están en memoria y se entregan sin demora artificial. La generación
de fragmentos y lectura de archivos están fuera. No mide red, HTTP, cola externa,
recepción de eventos reales, oráculo/IRM/EVM, builder ni inclusión. Se desglosan
assembly/verification/scenario/authorization y total por perfil y repetición.

R6 con `join` es un comparador de coste, no una alternativa con las nuevas defensas.
Ninguna diferencia se presenta como optimización equivalente o mejora operativa.
No se promueve R7 a operación sin testigo auténtico y validación representativa.

## Evidencia de estado

Se revisó el paquete técnico actual `NQC_031_R2_ONCE_VALORES_Y_DOS_CONTRATOS.zip`.
Sus 200 archivos cumplieron el manifiesto SHA256. Tiene 82 lecturas cubiertas,
incluidos 11 valores derivados de eventos, pero **cero pruebas de cuenta/storage**,
raíz exacta pretransacción null y chainId 4663. No sirve como testigo Ethereum
chainId 1/end_of_block para R5. `reference` conserva solo seis informes técnicos
originales y un inventario; no reconstruye contratos ni replica trabajo NQC031/032.

No se reintentó el acceso RPC 403 ni se cambió de ruta para eludirlo. Para avanzar
con estado real se necesita el paquete descrito en WITNESS_REQUIREMENTS, con
anclaje independiente. Oráculo/layout/IRM/ejecución y condiciones comerciales
siguen pendientes incluso si llegan las pruebas de almacenamiento.

Referencias primarias consultadas el 2026-10-19: https://eips.ethereum.org/EIPS/eip-1186,
https://eips.ethereum.org/EIPS/eip-1898 y
https://ethereum.github.io/execution-apis/api/methods/eth_getProof/.
