# Protocolo local fijado antes de ejecutar — 16/oct/2026

Incremento desde PR23 `085c88a20f9b9b0d1cea875833d19e84538b33e6`.
Objetivo acotado: ejecutar `simulateValidation` con el trazador oficial del bundler
v0.7 sobre Geth local y el account/paymaster exactos de la evidencia de ventana.
**No es ejecución completa de bundler, parser ERC-7562, mempool o servicio comercial.**

La instalación completa quedó bloqueada por red: Yarn no terminó y mostró cuatro
mensajes de reintento. Se intentó detener el proceso, que ya había desaparecido al
enviar SIGTERM. La revisión automática rechazó después la consulta al proceso de
instalación por riesgo de mantener tráfico tras la parada. No se reinicia ni se
cambia de proveedor. No están disponibles ethers y otras dependencias requeridas.
Se usa sólo el compilador TypeScript ya presente en caché para una función autónoma.
El paquete npm validation-manager@0.7.0 tampoco existe en la consulta realizada
(404); no se trató como un sustituto válido del repositorio fijado.

## Fuentes y mecanismo

- Bundler `eth-infinitism/bundler@1868538f1d7678576291d2ecabb4443c797ad133`.
  Se ejecutan su `bundlerCollectorTracer` y su serializador `getTracerBodyString`,
  sin modificar su lógica. Parser y ValidationManager se preservan para referencia,
  **no se ejecutan**. Tampoco se ejecuta Rundler.
- Account-abstraction `7af70c8993a6f42973f520ae0752386a5032abe7` y OpenZeppelin
  `dbb6104ce834628e473d2173bbc9d47f81a9eec3`, bytes verificados contra Git.
  `EntryPointSimulations` compilado con solc0.8.23 fijado, optimizer200/paris.
  ABI, layout, entrada completa y runtime quedan guardados.
- Geth1.17.8 commit `a579077007b98217c3e253a66e4b452ca0c32b96`. Descarga del host
  enlazado por la página oficial; firma PGP válida con huella publicada
  `FDE5A1A044FA13D2F7ADA019A61A13569BA28146`. No se afirma reproducibilidad del binario.
- TypeScript4.9.5 de caché; `transpileModule` sólo elimina tipos. No shims de ethers,
  reglas de seguridad desactivadas, parser reimplementado o modo `--unsafe`.

Geth arranca en genesis privado chainId4663, número0, timestamp1789786800,
Shanghai, sin peers/discovery. HTTP y Engine API sólo127.0.0.1. No fork ni conexión
a Robinhood. El estado original capturado se suministra por `stateOverrides` para
cada lectura, con los fixtures ya existentes de cuenta/router/ejecutor/paymaster;
EntryPoint se sustituye por su contrato oficial de simulación, como hace el bundler.
No se reproduce Nitro/ArbOS/DA ni se estima coste de ejecución comercial.
Se conserva íntegro el calldata y la firma pública del fixture. No nuevas firmas.

Los campos de stake adicionales son supuestos de laboratorio declarados, no estado
actual consultado. Los 1ETH/86400s del control financiado coinciden con los defaults
del bundler de referencia, pero este experimento **no prueba el mínimo comercial**.
La ruta no se ejecuta; sólo validación de cuenta/patrocinio. No se obtiene ingreso.

## Orden fijo de cinco controles

1. Ventana31s, depósito0.1ETH, stake0: observar retorno de EVM y acceso a budget slot1.
2. Mismo account/paymaster/calldata, stake fixture1ETH y delay86400s: observar stake
   devuelto y el mismo acceso. Financiación simulada; no aceptación de bundler.
3. Variante registrada de ventana1s, stake fixture: medir datos de validez devueltos.
   No interpretar retorno EVM como aceptación temporal del bundler.
4. Ventana31s con depósito0: control negativo, esperar revert con AA31.
5. Ventana31s con budgetRemaining0: control negativo, esperar BUDGET_POLICY.

Una sola ejecución. No ajustar resultados ni sobrescribir piloto. Un error RPC,
HTTP, límite o resultado inesperado detiene y conserva prefijo; los REVERT esperados
de controles4/5 son resultados EVM, no errores RPC. Guardar cuerpo de cada respuesta,
request exacta, hashes, orden, pausas, resultado parcial y logs de proceso.

Máximo global512 métodos locales/900s incluyendo arranque/esperas,350ms mínimos
entre inicios, sin HTTP paralelo, reintentos RPC, redirecciones o recuperación.
Timeout20s,2MiB por respuesta (retener prefijo límite+1). No endpoint remoto configurable.
Allowlist: web3_clientVersion,eth_chainId,eth_getBlockByNumber,debug_traceCall.
Plan normal:9 métodos locales;0públicos;0envíos. Comprobar el mismo hash/stateRoot
local antes/después. Cerrar proceso al terminar; no publicar base de datos/clave de nodo.

## Evaluación y límite

Se exige retorno ABI íntegro, firma de cuenta válida, prefund249541240000000wei,
contexto paymaster vacío, ventana exacta y stake conforme al control. El trazador
debe registrar SLOAD/SSTORE de slot1 del paymaster. La regla STO-031 del parser
fijado exige stake para ese acceso: es interpretación de fuente sobre nueva traza,
**no resultado de ejecutar el parser**. No llamar PASS a la admisión completa.

Fuente primaria de APIs nuevas: [Geth debug_traceCall](https://geth.ethereum.org/docs/interacting-with-geth/rpc/ns-debug),
[instalación oficial](https://geth.ethereum.org/docs/getting-started/installing-geth)
y CLI de Geth1.17.8. La página de descargas excedió el límite del buscador; se
consultó directamente su HTML para URL/huella. Se preservan recibos criptográficos,
no una copia completa del sitio. Las fuentes del bundler se leyeron de Git fijado.
