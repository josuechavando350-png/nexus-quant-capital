# NQC049 — puente offline hacia el verificador histórico real

19 de octubre de 2026. Base: NQC048 `ddbe6e300adc9127a5e257a7acdadab06f1b8241`. Rama única: `research/nqc-049-offline-nqc037-replay-20261019`. Solo se añaden archivos de este experimento; NQC037–048 y `main` no se modifican.

## Objetivo y avance

El código NQC048 conserva fragmentos y SHA-256 de respuestas sintéticas, pero su `verify` anterior no era el verificador real de NQC037. Esta entrega implementa `offline_bridge.py`, un puente **solo lectura y sin red**, que fija las fuentes históricas por Git blob SHA-1 y la especificación del plan NQC038 por SHA-256, reconstruye los fragmentos del registro NQC048, rechaza tamaños/códigos de base64 incorrectos, SHA discordantes, claves JSON duplicadas y envelopes erróneos y **solo entonces** llama al `intake.validate_step(operation, response, state)` auténtico de NQC037 cuando sus dependencias están instaladas.

El orden, IDs y propósitos del plan quedan enlazados a ocho operaciones exactamente; el registro debe indicar `DRY_RUN`, `commercial_admission=false` y los digestos originales. No existe función para abrir red, iniciar un presupuesto, pedir la clave, enviar o repetir solicitudes, alterar el journal ni habilitar una consulta posterior.

Una respuesta persistida `RECEIVED` válida se inspecciona, pero permanece `BLOCKED_RECEIVED_REVIEW_REQUIRED`. Una respuesta simulada como `SIM_ACCEPTED_1` jamás es una prueba válida de `eth_chainId` frente al verificador auténtico. Si el verificador rechaza una respuesta, `BLOCKED_NQC037_VALIDATION`. Un journal `RESERVED` o `REJECTED` también detiene la inspección.

## Validación realizada

Los archivos Python de GitHub se recuperaron y **sus Git blob SHA-1 coinciden byte por byte** con los originales que aprobaron `22/22` pruebas de Python 3.13 usando la biblioteca estándar. La suite `test_offline_bridge.py` prueba: integridad por fragmento y total, respuesta >650 KB dividida en tres, IDs, JSON inválido, prefix, novena reserva, falta/symlink de un fragmento, fuente modificada, eco de una respuesta falsa y revisión sin reenviar. Todos estos tests usan un **callback sintético** como sustituto deliberado del verificador original; el camino público `audit_repository` no admite sustituirlo.

La prueba del CLI con el directorio temporal sin el checkout íntegro devolvió `BLOCKED_PIN_OR_INPUT` y exit 2, como debe. Aquí no fue posible ejecutar el `intake.validate_step` real: no están instaladas sus dependencias `rlp` y `Crypto`, y la terminal no tiene resolución DNS a GitHub para recuperar un checkout integral. Se ha dejado el punto de integración exacto, **no** se afirma que el replay Merkle ya haya aprobado. Tampoco se ejecutaron en esta entrega las pruebas Python históricas, el aislamiento global o replay Nitro.

Reproducción en cualquier **checkout confiable con dependencias ya instaladas**, no desde el teléfono Android del usuario:

```sh
python -m unittest discover -s migration/experiments/nqc-049-offline-nqc037-replay -p 'test_*.py' -v
python migration/experiments/nqc-049-offline-nqc037-replay/offline_bridge.py --repo-root .
```

El segundo comando es de **solo lectura**; frente al fixture NQC048 existente, contiene deliberadamente la respuesta sintética `SIM_ACCEPTED_1`: el validador histórico **debe rechazarla**, no aceptarla como datos auténticos. El resultado no convierte `RECEIVED` en permiso para más consultas. El exit no cero es esperado en ese fixture.

## Acceso Triport: revisión de fuentes oficiales

Documentación inspeccionada sin consultar RPC:

- [eth_getProof Robinhood](https://triport.io/docs/robinhood/json-rpc/eth_getProof): declara `robinhood:rpc`, `x-token` y categoría de lectura pesada. Los límites por niveles publicados son políticas; una referencia antigua menciona Pro, de modo que el nivel efectivo de la clave sigue sin ensayarse.
- [Profundidad de archivo](https://triport.io/docs/robinhood/archive): dos pisos históricos medidos anteriores al bloque padre 66744161, **sin garantía por canal ni por bloque concreto**.
- [Límites Robinhood](https://triport.io/docs/robinhood/limits): el cuerpo HTTP tiene un tope publicado de 4 MiB; el límite local de 16 MiB no garantiza entrega de esa longitud desde el servidor.
- [Method explorer](https://triport.io/docs/platform/run-method): existe una ruta de diagnóstico autenticada con cookie de sesión y CSRF, que resuelve la clave por servidor, pero los valores de `chain` enumerados para esa ruta son `sol`, `eth` y `polygon`; la compatibilidad de Robinhood y la integración con nuestro ejecutor **no están demostradas**. No se han accedido ni trasladado cookies, sesión, CSRF o clave del navegador.

Por tanto, no existe aún un canal seguro y soportado para que **este ejecutor** utilice la clave Triport. El panel Android muestra credencial enmascarada y Robinhood LIVE, pero eso no proporciona acceso al ejecutor. La documentación tampoco sustituye una respuesta histórica autenticada. `TRIPORT_ACCESS_REVIEW.json` conserva cada alcance y URL.

## Criterio de cierre

**CERO** solicitudes Triport autenticadas, **CERO** pruebas históricas de estado, **0/11** slots autenticados en el corte exacto txIndex1, `commercial_admission=false`. Siguen pendientes canonicidad y finalidad independiente, witness completo, binario/configuración Nitro históricos, ejecución del prefijo y la economía de liquidaciones. Las 22 pruebas nuevas son pruebas de código, no de rentabilidad.

Siguiente acción significativa: conseguir un ejecutor con dependencias NQC037 completas y un **canal seguro de credencial**, demostrar que una única bitácora real gobierna las ocho lecturas entre interrupciones, y solo entonces ejecutar el plan fijo. **No iniciar lecturas mediante métodos o cadenas alternas ni por la interfaz del usuario fuera del control durable.**
