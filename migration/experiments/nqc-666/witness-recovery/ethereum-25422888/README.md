# NQC 666 — recuperación de una prueba pública de Morpho

Se recuperaron **una prueba de cuenta y una prueba de un slot**, junto con un
runtime de **15.623 bytes** obtenido de otra fuente pública. R5 verifica ambos
recorridos de trie contra la raíz publicada y el Keccak del runtime coincide
con el `codeHash` contenido en la cuenta probada.

**La raíz todavía no tiene anclaje canónico verificado.** Esto es recuperación
de evidencia parcial, no integración auténtica completa ni estabilización del
bot. R5 permanece predeterminado; R7 permanece experimental. Ninguno se modifica.

## Caso fijado

| Campo | Valor o alcance |
|---|---|
| Cadena declarada por el productor | Ethereum, chainId 1; no autenticada por la cápsula |
| Bloque declarado | 25422888; falta el encabezado completo |
| Cuenta | `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb` |
| Mercado declarado | `0x3274643db77a064abd3bc851de77556a4ad2e2f502f4f0c80845fa8f909ecf0b` |
| Borrower declarado | `0x6554874f13f5e953aee06ff38b501cf233e8f438` |
| Cobertura | Cuenta, compromiso de código y 1 de 9 slots R5 |
| Precio, intereses, elegibilidad y beneficio | Desconocidos |

Raíz publicada:
`0x1d15023066dcb9e977c40a0288f479bdaa0766206c9e781abe051cb63517c285`.

CodeHash probado relativo a esa raíz:
`0xfa259fa317198f88f5fa3c119f06c066295dbcd47d715e0a30e1bcf94c02ef8c`.

Se seleccionó este caso por disponibilidad de nodos de prueba publicados, no por
rentabilidad. Una captura NQC anterior de otro mercado en los bloques
26210229–26210231 mezclaba alturas de indexación y no aportaba nodos; no se mezclan
sus valores con este caso. El objetivo Nitro de NQC031 permanece separado.

## Procedencia y comprobación

La cápsula viene de `IlyasRidhuan/dogfooding`, commit
`f682b0ceeb8e2520cf04cf0d682ea2487db5ac4b`. El productor la describe como una
captura de Ethereum para una posición de demostración. La selección de mercado
y borrower está en su generador; NQC comprueba que ambos derivan exactamente el
slot contenido en la cápsula. La semántica del layout del runtime aún no está
atestada y no se certifican parámetros del mercado que no fueron probados.

El runtime viene de `EthereumPhone/PQ1`, commit
`4c8430458fbfb167b6a49a42e75db51ec6a7b66c`. Fue publicado junto con una captura de
otro bloque. Se aprovecha únicamente porque **sus bytes completos tienen el
hash comprometido por esta prueba de cuenta**; no se trasladan raíces, storage,
precios ni timestamps entre bloques.

Los dos archivos se preservan byte por byte en `reference/`. `PROVENANCE.json`
fija URL, commit, Git blob y SHA256. No se ejecutó código de los repositorios
fuente ni se instalaron dependencias nuevas. El formato de la cápsula se estudió
a partir de su generador; `recover.py` es una conversión offline propia y acotada.

La cápsula omite los dos nodos hoja. El conversor reconstruye sus preimágenes
RLP usando la clave restante y los campos explícitos. R5 exige que sus hashes
coincidan con los enlaces de los nodos padres hasta las raíces originales. No se
genera una raíz nueva para hacer pasar los datos. Solo se admite el formato
observado de nodos branch con referencias de 32 bytes; extensiones y otros
formatos se rechazan explícitamente.

La verificación relativa no prueba que esa raíz pertenezca al bloque declarado.
Una prueba cambia el número tanto en el archivo como en su selección y demuestra
que el vínculo de trie sigue siendo válido: el resultado conserva
`canonicality: UNKNOWN` y `header_verified: false`. La consulta pública del bloque
en Etherscan devolvió HTTP 403 y no se reintentó. La búsqueda estática de la raíz
exacta no encontró un encabezado utilizable; no es evidencia de inexistencia.

## Reproducir

Requiere Python y las dependencias fijadas en
`../../r3-state-evidence/requirements.lock`, ya usadas por R5. Desde este directorio:

```sh
sha256sum --check SHA256SUMS
python -B -m unittest discover -s tests -v
python -B recover.py \
  --capsule reference/morphoBorrower.capsule.json \
  --runtime reference/Morpho.ethereum.hex \
  --case CASE.json \
  --out /ruta/fuera-del-repo/nueva-recuperacion
cmp evidence/result.json /ruta/fuera-del-repo/nueva-recuperacion/result.json
cmp evidence/partial-account-proof.json /ruta/fuera-del-repo/nueva-recuperacion/partial-account-proof.json
```

La salida debe ser nueva. Código de salida 0 significa **solo recuperación de
prueba parcial relativa**. El resultado no es una captura R6/R7 y no se presenta
como paquete completo admisible por R5. Código 2 indica rechazo; no se emiten
hechos parciales como verificados cuando falla una comprobación.

## Pruebas ejecutadas

- **15 pruebas nuevas**: recuperación positiva, contraste con el recorrido R3,
  alteración de cada uno de los 12 nodos branch activos, cuenta, slot y runtime;
  cadena/mercado/borrower incorrectos, tamaños, padding, enteros no canónicos,
  claves duplicadas, extensiones no admitidas y salida cerrada ante errores.
- El verificador completo R5 rechaza el paquete de un slot por **storage proof
  coverage**, incluso usando un encabezado exclusivamente sintético de prueba
  para alcanzar esa defensa. Ese encabezado nunca se guarda como dato histórico.
- **75 ejecuciones de regresión R5**, incluidas sus 2.472 variantes diferenciales
  de trie, aprobadas. R3 y R5 comparten dependencias; este contraste no se presenta
  como auditoría independiente.
- **9 pruebas de aislamiento** y verificador de aislamiento aprobados.

Total: **99 ejecuciones de pruebas aprobadas**. Se reutilizó el binario nativo
de R7 con SHA256
`1cc575699de5a9395dc95b6cc17fbabae0c355459948ba91ef11d204ef0388f4`;
no se recompiló Rust ni se volvió a ejecutar su suite. Los logs están en `evidence/`.
El primer intento falló en tres casos positivos porque el archivo público divide
el hexadecimal del runtime en líneas. Se corrigió el lector para aceptar LF
acotados, conservando las fuentes intactas; el fallo inicial también se conserva.

## Lo que falta y siguiente operación concreta

`MISSING_WITNESS.json` identifica el bloque declarado, raíz que debe contrastarse,
cuenta y **los nueve slots exactos**, incluidos los ocho pendientes. Contiene
solicitudes de lectura para obtener chainId y encabezado; **no fueron enviadas**.
Después del encabezado verificado, las solicitudes de prueba y código deben
fijarse a su hash mediante la interfaz existente R6. Si el encabezado no contiene
la raíz publicada, se rechaza este caso; no se cambia el bloque para forzar una
coincidencia.

Faltan el anclaje canónico independiente, ocho pruebas de storage, atestación de
layout, dependencias y vigencia del oráculo/IRM y ejecución histórica completa.
Las condiciones financieras externas siguen siendo una autorización separada.
Una fuente accesible y autorizada que exporte ese testigo sigue siendo necesaria.

No se midieron nuevos nanosegundos: aún no existe el recorrido auténtico completo
que se pidió medir. Los benchmarks anteriores conservan sus límites. Esta
herramienta de recuperación no se incorpora al camino de decisión del motor,
no promueve una optimización, no consulta RPC y no habilita operaciones.
