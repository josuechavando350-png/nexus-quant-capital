# NQC042 — prefijo de bloque antes de tx0

Revisión offline del 19 de octubre de 2026, continuación de NQC041
`c8b9a675ff564b2ce82b6021f9f9a1fa61b9784d`. No se modifica ningún experimento
anterior ni el plan de ocho lecturas. No se adquirió estado histórico.

## Hallazgos materiales

**1. Abrir el estado no es una operación puramente de lectura.**
`ProduceBlockAdvanced` llama primero a `OpenSystemArbosState`. Su constructor
termina en `storage.KVStorage`, que ejecuta `SetNonce(account, 1)` para la cuenta
ArbOS. Con versión >=60 también abre el storage de transacciones filtradas y
hace lo mismo para **`0xa4b0500000000000000000000000000000000001`**.

La segunda cuenta no figura en el diagnóstico conservado ni en las pruebas
solicitadas por el plan autorizado. Se identificó mediante la declaración de
`FilteredTransactionsStateAddress`, no por inferencia de una dirección parecida.
El nonce 1 de ArbOS sí aparece en el diagnóstico. Una asignación puede ser
idempotente: **no se afirma que el nonce o stateRoot histórico hayan cambiado**.
La cuenta ausente tampoco se considera una cuenta inexistente. Para una
transición verificable hacen falta sus datos/proof y los nodos necesarios.

**2. Hay una transición de tarifas antes de construir tx0.**
`CommitMultiGasFees()` consulta el modelo activo en el estado padre. Solo si es
multigas copia nueve palabras `next[0..8]` a `current[0..8]`, incluyendo la
dimensión Unknown=0. Las direcciones exactas aparecen en `PREFIX_REVIEW.json`.
Ese layout es una hipótesis de rama, **no una escritura observada**.

El diagnóstico de NQC041 apunta a single en el preestado objetivo, pero no
prueba el modelo del padre. No se trasladan retrospectivamente esas longitudes
ni se supone que la copia multigas ocurrió o que fue omitida históricamente.
Si falta una longitud necesaria, el helper offline rechaza decidir la rama.

**3. La tarifa de contexto se captura antes de actualizar el modelo en tx0.**
Después de la copia condicional, el productor lee `BaseFeeWei`, construye la
cabecera y luego crea/ejecuta `startBlock`. El código de actualización de precios
modifica el storage, no reemplaza esa tarifa ya capturada en la cabecera.

Las dos cabeceras guardadas se revalidaron por RLP/Keccak contra sus hashes
observados. Sus valores son distintos:

| Posición | Base fee observada, wei |
|---|---:|
| Cabecera padre, bloque 66744161 | 67,350,000 |
| Cabecera objetivo, bloque 66744162 | 67,514,000 |

Con las semánticas candidatas, el valor esperado del slot L2/baseFee del padre
al crear la cabecera objetivo sería **67,514,000**, no la tarifa de la cabecera
padre. El slot es
`0xe54de2a4cdacc0a0059d2b6e16348103df8c4aff409c31e40ec73d11926c8202`.
No está en el diagnóstico ni en las cinco pruebas ArbOS del plan actual.
Esta igualdad es una **restricción derivada de fuentes y cabecera observada**,
no una prueba de almacenamiento contra la raíz padre. No se rellena el slot
faltante con ese valor para simular un witness completo.

## Secuencia de ejecución que debe preservar un futuro replay

| Fase | Efecto o límite |
|---|---|
| Apertura ArbOS | Lectura de versión y asignaciones de nonce; constructores auxiliares |
| Prefijo de precios | Selección de modelo; copia condicional next → current |
| Cabecera/contexto | Lectura de baseFee, captura de timestamp y poster; límites y preparación |
| Transacción interna | `StartTxHook` aplica `ApplyInternalTxUpdate`; retorna anticipadamente con cero gas |
| Después de tx0 | Finalización de transacción según configuración y reapertura/actualización de versión antes de seguir |

La rama interna retorna antes del `preCheck` ordinario, compra de gas y
`EndTxHook` de la ruta normal de geth. No se debe añadir artificialmente otra
actualización ordinaria de backlog/cobro a tx0 por tratarla como transacción
firmada convencional. Cero gas no significa cero efectos: se conserva el cuerpo
de `startBlock` revisado en NQC037/041. `ProcessParentBlockHash` también contiene
una finalización interna; las finalizaciones no equivalen a aplicar todas las
transacciones restantes ni a `FinalizeBlock`, que ocurre al final del bloque.

La observación de cabecera tiene ArbOS 61 en padre y objetivo, diferencia de
timestamp 1 y gasLimit `1<<50`. Son comprobaciones de consistencia condicionadas
a los hashes observados; no consenso ni identificación del binario histórico.

## Código y comprobación reproducible

`audit_prefix.py` produce la revisión estructurada, las dependencias conocidas
adicionales y las restricciones temporales. Reutiliza el mapper NQC041 y el
verificador de cabeceras NQC037 sin modificarlos. Los controles de orden son
anclas de texto del código revisado, **no ejecución Go ni análisis formal de
todos sus caminos**. Se preservan siete fuentes nuevas completas con Git blob
SHA y tamaño, más vínculos SHA-256 a fuentes/inputs previos.

Las fuentes siguen fijadas en Nitro
`3599acae1ad2fab4059fc46453c9cd3294126641` y su go-ethereum
`f3a977ddf30b138da2fe673ac5cbff2bc6dd4c88`. URLs en `SOURCES.json`; licencias
completas disponibles en el vendor NQC037 señalado allí. No se retocó código
upstream ni se detectó/corrigió un defecto del motor. Se precisó el contrato
pendiente del replay para no implementar un orden incorrecto.

Desde la raíz, con el entorno Python de investigación ya preparado:

```sh
python migration/experiments/nqc-042-block-prefix/validate.py
```

El comando escribe únicamente resultados NQC042 y no usa red. Las pruebas
nuevas alteran el orden de captura, dirección de copia, guardas de modelo,
asignación de nonce, salida anticipada y cabecera. También comprueban que los
datos ausentes no se promuevan a cero ni el informe a admisión comercial.
Pasaron **67 pruebas offline**: 12 nuevas, 14 del mapper, 32 del verificador
histórico y 9 de aislamiento, además del verificador de aislamiento. Logs y
hashes en `VALIDATION.json` y `evidence/`; no son pruebas históricas adquiridas.
No se compiló ni ejecutó Go/Nitro: Go no está disponible en este entorno. No
se instaló software al usuario ni se usó infraestructura adicional.

## Estado operativo y límites

La revisión de capacidades expuestas no encontró un nuevo canal soportado
para la credencial. No se repitió la transferencia fallida ni se accedió a la
clave. **Cero lecturas Triport autenticadas, cero pruebas históricas**; ninguna
consulta Blockscout. El proveedor no se considera fallido ni validado.
Siguen pendientes el canal seguro y el registro operativo durable único.

El plan de ocho consultas permanece byte por byte; este inventario no autoriza
consultas adicionales. `PREFIX_REVIEW.json` marca qué dependencias conocidas
faltan incluso en ese paquete parcial. No se afirma que la lista sea completa:
constructores, estimación de coste del poster, configuración de cadena y hooks
adicionales requieren revisión o ejecución real con detección de datos faltantes.
Las funciones extraPreTxFilter/extraPostTxFilter del candidato son no-op, pero
su propio comentario permite modificaciones del operador: otra razón para no
dar por identificado el binario histórico a partir de una imagen recomendada.

Próxima cuestión concreta: revisar la suficiencia del validador de proofs para
cuentas auxiliares y ausencias probadas, antes de añadir cualquier receptor de
witness más amplio. No seguir expandiendo una lista estática como si sustituyera
la ejecución. El estado exacto en txIndex1, replay Nitro y canonicidad independiente
siguen pendientes; **`commercial_admission=false`**.
