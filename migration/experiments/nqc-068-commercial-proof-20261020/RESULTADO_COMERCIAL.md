# NQC068 - Resultado comercial integral

**BLOCKED_EVIDENCE. Decisión: CONGELAR EL REPLAY. MALO para la meta de ingresos: rentabilidad propia no demostrada. No es una refutación económica del flash swap.**

Fecha del dictamen: 2026-10-20T16:36:49.670385+00:00. Padre revisado: `b5f263c3b620c7ad8f81f3a205288f52b0baf605`. Caso único: Ethereum 21762897 / tx índice 1 / `0x2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb`.

| Puerta | Dictamen | Evidencia |
|---|---|---|
| A. Original auténtico | BLOQUEADO | Se inició la reconstrucción EVM; tx0 no terminó por falta de storage tras rechazo 403 del túnel. |
| B. Principal propio cero | BLOQUEADO / NO EJECUTADO | No se ejecutó variante sobre baseline incompleto. |
| C. Neto contrafactual | NETO NO DETERMINABLE | Gas de variante, fills ejecutados y obligaciones no medidos. |
| D. Financiación comercial | PENDING / SPONSOR_UNCONFIRMED | Documentación pública de Titan; ninguna aceptación específica ni términos de responsabilidad NQC. |
| E. Ganancias reales NQC | NO DEMOSTRADAS | 0 de ganancia realizada demostrada en este expediente; ninguna operación NQC transmitida. |

## Avance verificable de este turno

El informe anterior de tres runs quedó desactualizado: el cuarto run `39453561233` había conseguido nueve respuestas dRPC y fallado localmente por `eth_blockNumber`. Recuperé íntegros sus 33 fragmentos comprimidos (SHA256 `89e0e2a89f8af22016ef94408262e45837749388b9968a34f6163ede8894229e`), ocho archivos y los nueve cuerpos RPC. Ninguno se había conservado en el informe anterior.

Se adaptó exclusivamente la inicialización local de Foundry: altura desde la cabecera histórica y precio desde el recibo original, ambos etiquetados como metadatos derivados. Los seis archivos fuente originales, Solidity y expectativas se conservaron byte por byte. Compilación local con Foundry 1.3.1 y solc 0.8.26. Se verificaron por cálculo los hashes de ambas cabeceras, los hashes de las 41 transacciones y su raíz `transactionsRoot`. Los firmantes de tx0/tx1 se recuperaron de sus firmas históricas, sin crear firmas.

La continuación conservó 37 cuerpos exitosos nuevos (una lectura inicial de saldo y 36 durante el fork). El intento siguiente falló al leer:

```
eth_getStorageAt(
  0x111111125421ca6dc452d289314280a0f8842a65,
  0x3,
  0x14c1350
)
URLError: <urlopen error Tunnel connection failed: 403 Forbidden>
```

El error lo produjo el túnel de conexión: no hay cuerpo JSON-RPC que permita atribuirlo al archivo de dRPC, a una cuota o a la retención del nodo. No se cambió origen, IP, sesión, credenciales ni transporte para eludirlo. La ejecución offline posterior, con las 46 respuestas exitosas conservadas y cero red, vuelve a detenerse exactamente en ese mismo slot. Baseline sin aprobar; variante sin ejecutar.

## Respuestas obligatorias al fundador

1. **¿Se reprodujo el original? BLOQUEADO.** Se intentó; la reconstrucción de tx0 no terminó. Exit code 1 y traza en `evidence/continuation_historical_metadata/baseline.log`; bloqueo reproducido en `evidence/offline_reproduction/`.
2. **¿Funcionó sin principal? BLOQUEADO.** No existe transacción local de variante ni estado inicial de un ejecutor nuevo efectivamente probado.
3. **¿Cuánto dejó neto? DESCONOCIDO.** Ningún neto de variante medido. Los 1.915425887007584330 ETH equivalentes pertenecen a una consolidación histórica condicionada de un tercero; no son resultado NQC.
4. **¿Quién financia gas? NO CONFIRMADO.** Titan describe patrocinio condicionado, pero no hay aceptación NQC, precio, prioridad de cobro ni cobertura acreditada de fallos/reorgs.
5. **¿Cuánto ganó NQC realmente? 0 demostrado en esta investigación.** El beneficio total real de NQC fuera de ella no fue auditado.
6. **¿Continuar o congelar? CONGELAR el replay online.** Hace falta un único paquete/testigo completo verificable del estado padre y dependencias de tx0/tx1, obtenido por vía permitida. Un slot aislado desbloquearía solo el primer acceso, no garantiza completar el caso.
7. **¿Es BUENO o MALO? MALO comercialmente hoy.** Bueno como avance de evidencia: se rescataron los datos y se localizó y reprodujo el bloqueo. No hay prueba de beneficio ni compromiso de financiación.

Confianza: **alta** en la identificación del bloqueo y en los datos íntegros conservados; **indeterminada** en la viabilidad/rentabilidad de la variante. No hay fundamento para asignar una probabilidad de ingreso ni proyectar mensualidades.

## Límites de autenticidad y aislamiento

Los hashes de cabeceras y transacciones no prueban por sí solos consenso ni la totalidad del estado. No se verificaron pruebas Merkle de cuentas/storage ni la raíz de los 41 recibos. Las respuestas RPC son evidencia primaria conservada de lo que el proveedor entregó, no un testigo canónico completo.

`main` permanece en `16e352225ba8a6a931834c4edf3d86d9a2924b7d`. El verificador del baseline pasa y sus nueve tests pasan. El verificador del árbol de investigación **falla** por el workflow activo heredado del padre revisado, sin modificarlo; sus tests dan siete aprobados y dos errores. Esta rama no activa ni modifica workflows. No se tocó ningún archivo previo, permisos, secretos ni otro repositorio. No hubo firma, broadcast, operación financiera, patrocinio solicitado ni gasto autorizado.

Ver `EVIDENCIA_CANONICA.json`, `CONTABILIDAD_INTEGRAL.json`, `REPLAY_ORIGINAL.md`, `REPLAY_CERO_PRINCIPAL.md`, `PRUEBAS_Y_AISLAMIENTO.md` y `BLOQUEOS_ACCIONABLES.md`.
