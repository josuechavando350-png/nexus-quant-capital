# NQC032-R4 — Cobertura por operación y corrección del verificador

**18/oct/2026, fecha operativa del proyecto. SOLO auditoría NQC032. NOT_PUBLISHED.**
No recompila ni modifica NQC031. No optimiza, importa ni cambia NQC666. No envía operaciones.

## Avance comprobado sobre una entrada nueva

Se recuperó el ZIP `NQC_031_R2_NET_ADAPTADOR_Y_ESTADO.zip` de Library y se verificaron sus **151 archivos cubiertos por manifiesto**, además del CRC del ZIP. Desde los registros originales `gate-prestate.json`, `adapter-prestate.json` y `inputs/08-prestate.json` se reconstruyó el inventario: **12 cuentas, 82 pares (dirección,slot), 71 valores observados coincidentes, 11 faltantes**. Dos de los 71 valores observados son cero explícito; los 11 ceros de Anvil no sustituyen valores históricos. Tres cuentas del inventario tienen código pero no slots leídos; no deben desaparecer por aplicar un filtro de “cuentas con almacenamiento”.

El listado de prueba generado coincide con `ESTADO_HISTORICO.json` del productor. Esto es una comprobación independiente, **no un nuevo descubrimiento de datos on-chain**. No se obtuvo ninguna prueba histórica de las 12 cuentas ni de los 82 slots. Tampoco una raíz autenticada anterior a tx1.

**Corrección de continuidad:** los 11 faltantes son acumulados de PairOracle de la integración de lectura del oráculo. No se ha reconciliado una reducción de 19 a 11. Los 19 supuestos de direcciones nuevas de R1 pertenecían a otra ejecución/alcance; esta revisión no los descarga ni los suma automáticamente a los 11. `COVERAGE.json` separa datos ausentes de datos no autenticados.

## Corrección propia de R3

El padding Keccak-256 original era incorrecto cuando `len(input) % 136 == 135`: producía un bloque adicional en lugar de combinar los bits de padding. El nuevo archivo `source/state_proof_r4.py` es una copia con un overlay acotado; el original en `vendor/r3` permanece intacto.

Se contrastaron **413 longitudes** con `CompactFIPS202.py` del equipo Keccak/XKCP, blob Git `0b9608fc01852ea94182139890beca21b61b677a`; la copia local tiene ese mismo blob. Se usa sufijo `0x01` (Keccak), no `0x06` (SHA3). R3 difiere en 135, 271, 407 y 543 bytes dentro de esa rejilla; R4 coincide en todas. Una prueba de cuenta sintética con código válido de 135 bytes reproduce un rechazo incorrecto de R3 y su corrección en R4. La referencia SHA3 se contrastó adicionalmente con `hashlib.sha3_256` en siete longitudes.

**No se encontró discrepancia de hash en los 12 runtimes capturados de este inventario.** No se extiende esa conclusión a todos los artefactos anteriores. No hay evidencia de incidentes, robo, fallo de Morpho/Titan ni error de los dos Astra. El arreglo es de nuestro verificador local.

## Integración de alcance

`proof_ingress.py` utiliza el inventario completo y un digest de política suministrado aparte del paquete. Vincula cadena, bloque/hash, transacción/índice y fase pretransacción; exige cuentas incluso sin slots y todos los pares solicitados. Reutiliza las primitivas MPT/RLP de R3 con el padding corregido. Las pruebas sintéticas de 11, 19 y 82 pares prueban que no se depende de un contador fijo.

Una política cuya raíz exacta es desconocida no toma la raíz del paquete, del padre ni del final del bloque. Una prueba parcial rechazada no publica hechos parciales como verificados. Una prueba completa de nuestro dominio sintético puede dar `PROOF_LINKS_VALID_CONFIGURED_SCOPE_ONLY`, pero **nunca** consenso, contexto Nitro, autenticación de pagos, beneficio ni autorización comercial. El modelo de pruebas de la cadena 4663 y el vínculo de su raíz requieren revisión externa adecuada.

El inventario real sólo cubre **la integración de lectura del oráculo**, no el futuro candidato económico entero. Las etiquetas de contexto quedan contrastadas con la configuración; el verificador no demuestra por sí solo que esa raíz pertenece a ese bloque/instante.

## Reproducir sin red

Requiere Python 3.10+; no paquetes externos para las pruebas/análisis. Los originales se distribuyen sellados; no se ejecuta código Solidity ni se levanta un nodo.

```sh
python -B verify_manifest.py
python -B reproduce.py --out /tmp/nqc032-r4-una-carpeta-nueva
```

La salida debe ser nueva y estar fuera de la entrega. Produce los registros de 40 pruebas nuevas, 42 regresiones R3 sobre la copia corregida y cuatro JSON deterministas. No sobrescribe evidencias selladas. La verificación de manifiesto se repitió después de la reproducción limpia.

## Alcance de las pruebas y controles no ejecutados

- **40** pruebas nuevas; una contiene 413 comparaciones de longitudes. No se cuentan como 413 tests adicionales.
- **42** pruebas heredadas de R3 ejecutadas sobre la copia corregida. El script sólo redirige el nombre del módulo importado; las fuentes de las pruebas no cambian.
- Verificación de integridad de los 151 archivos Astra y los 15 del manifiesto original R3, seguida de comparación byte a byte tras el trabajo.
- El verificador global de aislamiento del repositorio **NO_RUN**: esta entrega no es un checkout completo del repositorio. No se atribuyen aquí las 9 pruebas de aislamiento archivadas por Astra.
- **NO_RUN:** compiladores, Solidity, Nitro, RPC, nuevas liquidaciones, benchmarks, evidencia financiera externa y pruebas históricas auténticas. No hay escrituras remotas ni ejecución entre turnos.

**Decisión real:** `EVIDENCE_INCOMPLETE_NO_COMMERCIAL_ADMISSION`. Financiación, titularidad, conversión, costes completos y resultado económico propio siguen sin cerrar. No hay nuevo ingreso acreditado; mensual no estimable. No se eleva confianza comercial por este trabajo.
