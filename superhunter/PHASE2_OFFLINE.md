# Fase 2 de SuperHunter · Canto

En el DEX de septiembre de 2022, dos de los siete hallazgos de la clave tienen una alerta de Slither que señala la causa en la operación correcta. En Canto Identity, ninguno de los cinco tiene una coincidencia en las salidas disponibles. Con el ZIP corregido, las cinco herramientas estáticas de Identity produjeron salidas. Un detector de Slitherin falló. Las tres campañas de ityfuzz quedaron sin medir.

Los títulos cortos y las severidades de las tablas proceden de las claves adjuntas. El cotejo usa la alerta que produjo cada herramienta. Para dar crédito se exige la misma operación y el mismo mecanismo del juez. En la primera medición se conservaron las salidas de los análisis antes de cotejar las claves. En la repetición con el ZIP corregido ya se conocía la clave y se mantuvieron las reglas originales. Al ver que la clave de Identity añadía un cuarto archivo al alcance del README, se repitieron los análisis de fuente sobre los cuatro, con las reglas originales. Todas las compilaciones y pruebas de este estudio se ejecutaron en un espacio de red aislado.

[Expediente con las huellas de los ZIP y las fuentes, los resultados de las reglas, las alertas acreditadas y las salidas de Foundry](product_supply/c4-phase2-canto-evidence.json)

## Canto DEX y Oracle · septiembre de 2022

| ID del juez | Título corto de la clave | Localización de SuperHunter |
|---|---|---|
| H-01 | Pegs USD hardcodeados se pueden romper | Sin coincidencia. Las alertas de literales no identifican la dependencia económica del peg. |
| M-01 | DoS por loop sin límite | **Slither**, `calls-loop`. Identifica la llamada por cada elemento de `allPairs` en `BaseV1Factory.setPeriodSize()`, línea 565. El bucle se extiende hasta `allPairs.length` en la 564. La regla documenta el riesgo de denegación de servicio. |
| M-02 | `token0TVL` puede dar cero en ciertos casos | **Slither**, `divide-before-multiply`. Señala la división entera previa a la multiplicación en la asignación de `token0TVL`, línea 582 de `getPriceLP()`. |
| M-03 | Tokens con nombres de stablecoin para suplantar | Sin coincidencia con el uso del nombre como identidad en `getUnderlyingPrice()`. |
| M-04 | Period size no se actualiza al crear par | Sin coincidencia en `createPair()`. |
| M-05 | `getUnderlyingPrice()` debería dar 0 al fallar | Sin coincidencia con el comportamiento de retorno requerido. |
| M-06 | Sin checks de downtime del sistema | Sin coincidencia con la ausencia de validación de las observaciones después de una interrupción. |

**Resultado observado: 0/1 High y 2/6 Medium.** Slither analizó el grafo de compilación de Solidity 0.8.11 con 12 unidades de fuente. El cotejo se restringió a los dos archivos del alcance. Los 179 avisos de Slither y los 55 de Slitherin incluyen dependencias. Aderyn emitió avisos de orden aritmético en otras líneas del contrato core. 4naly3er señaló una posible división entre cero en la línea de M-02. Ninguno de esos avisos recibe crédito por el truncamiento en `token0TVL`.

| Herramienta | Ejecución y cobertura |
|---|---|
| Slither 0.11.6 | 101 detectores, 26 contratos analizados, 179 avisos en el grafo. |
| Slitherin | El lote de 29 falló en `pess-nft-approve-warning` con `TypeError: 'LibraryCall' object is not subscriptable`. La repetición con los otros 28 terminó y produjo 55 avisos. |
| Aderyn 0.6.8 | 88 detectores, 2 archivos, 20 grupos con avisos. |
| 4naly3er | 169 reglas con el AST compilado de los dos archivos, 67 grupos con avisos. |
| Semgrep 1.169.0 | Una regla de NQC, `nqc-token-call-review`, la misma del ensayo anterior. Dos archivos leídos, dos avisos, cero errores. |
| ityfuzz completo | Sin ejecución. 0 iteraciones, 0 segundos. |

[Informe oficial citado por la clave del DEX](https://code4rena.com/reports/2022-09-canto)

### Prueba aritmética del par estable

Foundry 1.10.0 ejecutó **1 100 002 casos en 7,413 segundos de reloj acumulados** para cuatro invocaciones, incluida la compilación cuando correspondió. Cada una tenía un límite de cinco minutos y terminó al agotar los casos. La función `_k` del ensayo conserva los bytes de las líneas 439–449 de `BaseV1-core.sol`. Las reservas son sintéticas y los tokens se normalizan con 6 y 18 decimales.

| Propiedad y dominio | Semilla | Casos | Tiempo de reloj |
|---|---|---:|---:|
| Fórmula exacta en múltiplos de 0,001 token, entre 0,001 y 1 000 tokens por reserva. Simetría y monotonía al incrementar la primera reserva. | `0x202209` | 100 000 | 2,276 s |
| Redondeo fuera de esa cuadrícula, desde una unidad mínima hasta un token por reserva. Monotonía al incrementar cualquiera de las reservas. | `0x202209` | 333 334 | 2,878 s |
| Mismas propiedades y dominio de redondeo | `0xc40001` | 333 334 | 1,072 s |
| Mismas propiedades y dominio de redondeo | `0xc40002` | 333 334 | 1,187 s |

En el segundo ensayo, el valor de referencia se obtiene expandiendo el polinomio y dividiendo al final. En ese dominio se comprobó que el resultado de Solidity queda entre la referencia entera y cuatro unidades por debajo de ella. Los cuatro procesos terminaron con código 0. El contador corresponde a ejecuciones, y puede incluir entradas repetidas. Estas pruebas ejercitan la función matemática aislada. La conservación del invariante a través de un swap, las transiciones del pool y el estado histórico quedaron sin medir.

Extracto literal de Foundry. La salida íntegra de las cuatro invocaciones y las fuentes del ensayo están en el expediente.

```text
[PASS] testFuzz_polynomial(uint32,uint32) (runs: 100000, μ: 12416, ~: 12416)
[PASS] testFuzz_rounding(uint64,uint64) (runs: 333334, μ: 11979, ~: 11979)
```

## Canto Identity · enero de 2023 · ZIP corregido

**Resultado de la repetición: 0 de 1 High y 0 de 4 Medium.** El ZIP corregido aportó las fuentes de Solmate, ds-test y forge-std. Los cuatro contratos de la clave y la propia clave conservan los mismos bytes que en el ZIP anterior. La cuarta fuente, `CidSubprotocolNFT.sol`, figura fuera del alcance en el README y dentro en la clave. El compilador produjo el AST con tipos y el bytecode sin errores. La tabla usa las alertas de esta repetición.

| ID del juez | Título corto de la clave | Salida de las herramientas y decisión |
|---|---|---|
| H-01 | Frontrun de mint+add para robar el NFT | Slither, Aderyn y 4naly3er señalaron llamadas en el bucle de `mint()`. Las alertas no identifican el adelanto de la operación ni la apropiación del NFT. Sin crédito. |
| M-01 | AssociationType ORDERED o PRIMARY puede sobrescribir | Slither y Aderyn señalaron riesgo de reentrada en `add()`. Ninguna alerta señaló la sobrescritura de la asociación. Sin crédito. |
| M-02 | Varias cuentas pueden tener la misma identidad | Aderyn señaló una llamada seguida de un cambio de estado en `register()`. Ninguna alerta identificó la falta de unicidad. Sin crédito. |
| M-03 | Riesgo de griefing en el mint | Los avisos de bucle, llamada y reversión en `mint()` no describen cómo otra operación puede frustrar la acuñación. Sin crédito. |
| M-04 | tokenURI roto | Aderyn marcó colisión de hash y 4naly3er sugirió cambiar la concatenación en la línea 140. Ninguno explicó que el ID numérico se incorpora en binario y la URI necesita su representación textual. Sin crédito. |

| Herramienta | Resultado offline |
|---|---|
| Solidity 0.8.17 | 7 unidades de fuente, 8 contratos e interfaces, 0 errores. Se usaron los remapeos del archivo adjunto. |
| Slither 0.11.6 | 101 detectores, 65 avisos en el grafo compilado, incluidas sus dependencias. Se utilizó el build-info del compilador. El adaptador usó las rutas predeterminadas al faltar la CLI de Hardhat. |
| Slitherin | El intento con 29 detectores falló en `pess-nft-approve-warning`. El reintento con los 28 restantes finalizó con 8 avisos. |
| Aderyn 0.6.8 | 88 detectores sobre los 4 archivos, 9 grupos de avisos. |
| 4naly3er | 169 reglas con el AST compilado de los 4 archivos, 37 grupos de avisos. |
| Semgrep 1.169.0 | Una regla de NQC sobre los 4 archivos, 0 avisos y 0 errores. |

[Huellas del ZIP corregido y de las fuentes, resultados por regla y diagnósticos de ityfuzz](product_supply/c4-identity-fix.json) · [Medición anterior con el ZIP incompleto](product_supply/c4-phase2-canto-evidence.json)

[Informe oficial citado por la clave de Identity](https://code4rena.com/reports/2023-01-canto-identity)

## Campañas dinámicas y medición anterior de LendingLedger

El ejecutable completo de ityfuzz no estaba instalado en el entorno. La comprobación de disponibilidad terminó con código 127, stdout vacío y esta salida real de la shell.

```text
sh: 1: ityfuzz: not found
```

Se comprobó la instalación desde las fuentes fijadas por NQC en `80e3b44170573b592cd53b2c5ee9f36b21032b16`. Al resolver el archivo de bloqueo sin red, Cargo terminó con código 101 antes de compilar. La primera dependencia ausente fue `move-binary-format` en la revisión `a88e9595de3c04a540c059d5f4b6d148419c508c` de `ityfuzz-sui-fork`. La resolución se detuvo ahí, por lo que la lista de dependencias faltantes puede ser mayor. Extracto literal de Cargo:

```text
failed to load source for dependency `move-binary-format`
```

Para comprobar la instalación sin Internet haría falta una distribución completa de ityfuzz para Linux x86_64 con sus bibliotecas de ejecución y una huella verificable, o la revisión fijada con todas sus dependencias locales de Cargo y el toolchain `nightly-2024-01-01` indicado por el proyecto. Para evaluar estado histórico también hace falta una captura local verificable con el bloque, la raíz, el código y el almacenamiento de los contratos implicados. Un arranque del binario por sí solo acreditaría su disponibilidad.

Los ZIP nuevos no aportaron un snapshot identificado por bloque y raíz de estado. El ensayo de Foundry y la utilidad de inspección de opcodes no se contabilizaron como ejecuciones de ityfuzz. Para los dos concursos nuevos y LendingLedger, el fuzzer completo consumió **0 segundos y 0 iteraciones por concurso**. La capacidad de ityfuzz para alcanzar los hallazgos sigue sin medir.

| Canto 2024-01 · hallazgo del juez | Alcance dinámico de ityfuzz | Localización dinámica de la causa |
|---|---|---|
| H-01 · Peso de mercado incorrecto | Sin medición | Sin medición |
| H-02 · Cálculo incorrecto del siguiente período | Sin medición | Sin medición |

Se verificaron los ocho archivos de la captura previa de LendingLedger. El campo histórico `tools.ityfuzz.fuzzing_executed` vale `false`. SHA-256 del ZIP previo: `209663693febe6624148a0f57ad0d89d0addadc27293bc0189820d52195e0c5a`.

[Expediente histórico de LendingLedger](product_supply/c4-canto-2024-01.json) · [Informe oficial](https://code4rena.com/reports/2024-01-canto)

## Verificación de NQC

El perfil preparado pasó las 490 pruebas del producto y las 13 del toolkit, sin omisiones. El verificador de aislamiento comprobó 642 archivos históricos y pasó sus nueve pruebas. Antes de cargar todos los componentes locales, el perfil de producto omitió 27 pruebas. Una repetición intermedia dio dos errores por faltar `rustc` en el PATH. La repetición completa utilizó el compilador local fijado por el repositorio.

El barrido general independiente de `superhunter/tests`, ejecutado con el runtime del toolkit, **falló**. La salida final de unittest fue:

```text
Ran 3814 tests in 526.299s

FAILED (failures=82, errors=204, skipped=27)
```

En 153 trazas aparece `unsupported inherited unittest inventory`. También hay fallos de inventario de fuentes, de validación de snapshots y de disponibilidad de la plataforma sellada. El PR documenta la medición de los concursos. La suite general queda en rojo. Las cuentas por módulo y la huella de la bitácora figuran en el expediente.
