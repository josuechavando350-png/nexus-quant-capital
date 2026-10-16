# Resultado: parada local conservada y defecto del adaptador identificado

16/oct/2026. PR24 continúa PR23. Protocolo publicado **antes** de ejecutar:
`dae502a2d0f26ce16a7a9d286ff889fb26d5af42`, árbol
`5cc5a66e2340ccc67bd7bdb04b71668c268a477f`. Sus 24 fuentes siguen intactas.
Una captura local, salida 1; no se relanzó ni sustituyó el piloto.

| Medida | Observado |
|---|---:|
| Métodos RPC locales / HTTP | 4 / 4 |
| RPC públicos / transacciones enviadas | 0 / 0 |
| Duración de proceso | 1.532053798 s |
| Esperas de admisión incluidas | 1.036228139 s |
| Separación mínima entre despachos | 350.150358 ms |
| Intentos `simulateValidation` | 1 de 5 controles previstos |
| Controles de validación completados | 0 |
| Llegó a validar el paymaster | No |
| Comprobación final de cabecera | No se alcanzó |

El primer control devolvió `FailedOpWithRevert(0, "AA23 reverted", 0xf645eedf)`.
El error interior corresponde a `ECDSAInvalidSignature()`. El trazador registra una
llamada a la dirección nativa `0x…01` que devuelve bytes vacíos y consume 0 gas.
El hash de operación observado coincide con el fixture aprobado; su calldata y
firma pública se conservaron. El fallo no prueba rechazo de stake, del paymaster
ni admisión comercial. Tampoco invalida por sí solo las simulaciones Nitro previas.

## Diagnóstico y preparación offline

El adaptador copió el saldo histórico y almacenamiento vacío de `0x…01` a
`stateOverrides`. El código de Geth fijado elimina una dirección de la tabla de
precompilados cuando aparece en ese mapa, aun si sólo se modifica saldo/estado.
Por eso la copia desactivó accidentalmente la recuperación nativa de firmas.
Es una conclusión sustentada por fuente y traza; aún falta una captura corregida.

Fuente primaria fijada:
[Geth override.go](https://github.com/ethereum/go-ethereum/blob/a579077007b98217c3e253a66e4b452ca0c32b96/internal/ethapi/override/override.go),
blob Git `d3644570325c499d40af7006d4e409ab8067476b`, preservado completo en
`evidence/diagnosis/geth-override.go`. El auditor verifica ese blob y todos los
cuerpos RPC, reproduce exactamente la parada y rechaza atribuir resultados al
paymaster. No se ejecutó el parser del bundler.

`prepare_next.py` es una propuesta **offline, no conectada al runner registrado**:
traslada el saldo de precompilados nativos a genesis y los excluye del mapa de
overrides, conservando los demás bytes, la firma y los contratos. Rechaza código,
almacenamiento no vacío, movimientos de precompilados y colisiones de genesis.
No sustituye `ecrecover`, no evita comprobar firmas y no desactiva reglas del bundler.
Se prepararon las cinco variantes, pero **ninguna variante corregida se ejecutó**.
Integración y nuevo protocolo previo son requisitos para la siguiente captura.

## Bloqueo distinto: bundler completo

Yarn no terminó de obtener las dependencias del repositorio fijado y produjo
cuatro mensajes de reintento de red, preservados. El intento de detener el proceso
encontró que ya había finalizado. La revisión automática rechazó posteriormente
consultar la sesión del instalador por riesgo de mantener tráfico tras la parada.
No se retomó la instalación ni se cambió de proveedor. Faltan dependencias como
`ethers`; **ValidationManager, parser ERC-7562, depósito agregado y mempool no se
ejecutaron**. Geth y el trazador autónomo ya disponibles permitieron este incremento.

La lectura de la fuente preservada del bundler v0.7 indica que la validación temporal
exige más de 30 s restantes y que STO-031 requiere stake para ciertos accesos al
almacenamiento propio del paymaster. Son reglas leídas, no resultados de esta
captura. La prueba no alcanzó el paymaster y no estableció stake mínimo, depósito
mínimo ni disponibilidad de un financiador. Los fixtures 0.1 ETH/1 ETH no son fondos.

## Verificación y límites

45 pruebas Python distintas aprobadas: 14 preparatorias, 6 del diagnóstico/propuesta,
16 regresiones de ventana y 9 de aislamiento. El auditor offline reconstruye el
prefijo real. 19 manifiestos anteriores, 377 blobs originales y 24 fuentes fijadas
sin cambios; 106 workflows deshabilitados, 0 activos. Se compiló la dependencia
oficial EntryPointSimulations; no se cambiaron contratos NQC, no se ejecutaron
pruebas Solidity ni Rust en este incremento.

El primer intento de importar la clave PGP tuvo un error al arrancar gpg-agent;
la verificación posterior de la firma fue válida y ambos recibos se conservaron.
`git diff --check` señala un espacio final en `Comment: Hostname: ` de la clave PGP
original importada. Se preservan sus bytes; no es un cambio de código propio.
Los logs de Geth no incluyen zona horaria: no se atribuye UTC a su hora de pared.

Geth cerró al detenerse; su base de datos y clave de nodo no se publican. No hubo
RPC Robinhood, envío, firma nueva, gasto, cuenta o suscripción. No se midieron
oportunidades, Nitro/DA, gas comercial, financiación disponible ni rentabilidad.
La confianza es alta en el defecto del adaptador; la aceptación corregida sigue
pendiente. Una ruta sin inventario propio aún necesita quien financie gas y fallos.
