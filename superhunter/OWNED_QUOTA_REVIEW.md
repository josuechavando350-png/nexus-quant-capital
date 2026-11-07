# Evaluación defensiva de un libro de cuotas propio

Este laboratorio contiene seis variantes fijas de `OwnedQuota`: dos controles
correctos y cuatro defectos sembrados conocidos. Una liberación válida debe
descontar la misma cantidad de cuota y saldo, acreditar las unidades distribuidas
y conservar el total. La cantidad cero y el límite exacto son válidos; exceder la
cuota o saldo revierte. Agotar gas no debe persistir cambios.

El detector recibe exclusivamente estado anterior/posterior, cantidad, gas,
resultado y retorno. No recibe la etiqueta, variante, bandera de hallazgo o
fuente del caso. Identifica descuento de cuota ausente, doble descuento de saldo,
crédito de más y rechazo indebido del límite. Las etiquetas se incorporan después
de calcular las predicciones. Errores de evidencia o cobertura bloquean el
informe; no se convierten en negativos ni en una evaluación perfecta.

## Ejecutar y verificar

Usar el entorno QA fijado y los mismos solc/Geth de `NATIVE_DOCTOR.md`.
El digest procede del recibo QA generado sobre estos bytes exactos.

```sh
python -m superhunter evaluate-owned-quota --solc /herramientas/solc --evm /herramientas/evm --source-digest DIGEST --out /evidencia/cuotas
python -m superhunter verify-owned-quota --solc /herramientas/solc --evm /herramientas/evm --source-digest DIGEST --bundle /evidencia/cuotas
```

El segundo comando recompila y vuelve a ejecutar todos los controles en un
proceso nuevo; comprueba los bytes del paquete completo, no solo su resumen.
Un informe manipulado y vuelto a sellar no sustituye las observaciones
regeneradas. Ambos comandos ejecutan únicamente código propio fijo; no aceptan
fuentes, contratos, objetivos, RPC, transacciones ni calldata externos.

## Unidad de medida y límites

- Seis casos = seis variantes de fuente; dos compilaciones por variante, doce
  constructores y 228 llamadas son observaciones correlacionadas, no 228 casos.
- Seis secuencias fijas incluyen cero, límite exacto, exceso, repeticiones y gas
  insuficiente. No son búsqueda exhaustiva ni un conjunto oculto.
- Se calcula matriz TP/FP/TN/FN y errores/abstenciones con el contador de benchmark
  existente y un segundo recuento basado en conjuntos. También se comparan dos
  ablaciones: observar solo el resultado o solo los cambios de estado.
- Un fallo del detector puede producir falsos negativos: `OWNED_QUOTA_EVALUATED`
  significa que se calculó la evaluación, no que el detector sea perfecto.
- Los errores de formato, cobertura, compilación o ejecución bloquean el paquete.
  Un proceso bloqueado no genera matriz de confusión ni se omite del informe de
  ejecución. No se afirma ausencia de errores operativos por un paquete ausente.
- El worker conserva 180 s de pared, 90 s CPU, 2 GiB de memoria, límite de archivo
  de 20 MiB y salida de 4 MiB. Usa una caché Python nueva y privada.
- La imagen Geth fijada de 42,001,080 bytes se sella en memoria antes de iniciar
  ese worker. El descriptor heredado se comprueba por sellos, tamaño y hash en
  cada uso; no se reescribe dentro del límite de archivo de 20 MiB ni se amplía
  ese límite. Los procesos nativos conservan su límite de salida de 2 MB. El
  worker específico de cuotas usa 2 GiB y no eleva el límite heredado. Los
  archivos del motor histórico y sus capturas se conservan byte por byte: sus
  identidades no se sustituyen para presentar capturas antiguas como nuevas.
- Es un solo motor Geth/Cancun con solc compartido. El replay en otro proceso no
  demuestra independencia de motores, productores, aislamiento del host, un
  hallazgo original, impacto económico real ni generalización.

El estudio complementa los cuatro casos de pausa/acceso, que se conservan
íntegros. No se suman ambos estudios para afirmar una precisión global.

## Criterio de aceptación del corpus conocido

El detector completo debe producir 4 TP, 2 TN, 0 FP y 0 FN sobre estos seis
casos. La ablación que solo observa el resultado debe mostrar 1 TP y 3 FN;
la que solo observa estado, 3 TP y 1 FN. Ambos controles correctos deben seguir
siendo negativos en las tres evaluaciones. Estos valores son criterios del
corpus conocido, no conclusiones sobre programas ajenos. El código de evaluación
conserva los conteos realmente calculados aunque incumplan esos criterios.
