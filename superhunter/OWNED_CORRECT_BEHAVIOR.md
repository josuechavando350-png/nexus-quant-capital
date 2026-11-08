# Comportamiento correcto sobre los contra-controles fijos

Este perfil añade ejecución del **modelo abstracto correcto** a los 16 casos
fijos del corpus de contra-controles v1. El informe anterior sigue describiendo
solo entradas; no se modifica ni se convierte retroactivamente en ejecución.

`owned_authority_behavior.py` ejecuta exclusivamente `simulate('correct', ...)`.
No selecciona variantes defectuosas ni acepta entradas, fuentes, destinos o
contratos externos. Grant/revoke son comandos confiables del laboratorio;
los nombres de principal son campos abstractos, no identidades autenticadas.

## Tres formas de comprobar el resultado

1. Una tabla escrita explícitamente fija las decisiones y el contador acumulado
   esperado después de cada evento. No consulta los resultados del modelo.
2. El modelo incremental existente calcula decisiones y efectos desde los eventos.
3. La referencia existente consulta el historial para calcular las decisiones.

El modelo y la referencia reciben únicamente copias de los eventos. Nunca
reciben los índices de cobertura, las respuestas esperadas o las etiquetas de
los casos históricos. El informe exige coincidencia exacta con la tabla,
incluidos tipos, orden, efectos antes/después y los cuatro contadores.
La referencia comparte la misma política abstracta; no es una especificación
independiente de esta política ni un productor autenticado independiente.

## Semántica que se comprueba

- Grant y revoke se aceptan sin producir efectos de uso.
- Un uso sin concesión o con concesión revocada se rechaza sin efectos.
- Tras otra concesión, una credencial de generación anterior sigue siendo inválida.
- Principal y ámbito deben coincidir. Los contadores de otros ámbitos quedan intactos.
- Cada uso aceptado incrementa un único contador exactamente en uno.
- Repetir una credencial vigente está permitido por esta política: ambos usos
  producen su efecto. Este perfil no representa credenciales de un solo uso.

El papel `present`/`absent` describe presencia de una condición de entrada,
**no** aceptación/rechazo del modelo. Por ejemplo, la generación no emitida
tras una revocación no satisface la condición de cobertura de credencial vieja,
pero su uso sigue siendo rechazado. Las dos dimensiones se conservan separadas.

Los 16 casos contienen 13 secuencias distintas y conservan sus duplicados.
Los once casos históricos y sus etiquetas mantienen su hash fijado, incluida
la omisión `latent_revocation`. Aquí no se ejecuta un detector ni se recalculan
TP, TN, FP o FN. Tampoco se ejecutan EVM, compiladores o contratos por generar
este informe. Cualquier aceptación nativa del corpus histórico se documenta
separadamente, identificada por el digest de la versión.

## Evidencia y CLI

Se escribe un bundle nuevo fuera del checkout con entradas y expectativas,
trazas, evaluación, resumen y manifiesto. El verificador vuelve a calcular las
trazas y comprueba bytes, inventario y código antes/después. Recalcular hashes
no permite sustituir una decisión, expectativa o afirmación de alcance.

```sh
python3 -B -m superhunter review-owned-correct-behavior --out /ruta/privada/comportamiento
python3 -B -m superhunter verify-owned-correct-behavior --bundle /ruta/privada/comportamiento --expected-source DIGEST_ESPERADO
```

El digest vincula código y datos; no prueba integridad de memoria, autoría o
independencia del host. El resultado no acredita una vulnerabilidad, seguridad
de un sistema real, cobertura general, integración en producción o avance
global de SuperHunter. Los resultados ejecutados se anotan en `CONTINUATION.md`.


## Validación de esta entrega

31 pruebas focalizadas PASS: las 29 nuevas y las dos regresiones existentes
que comparan las entradas directa y por paquete de QA. El primer pase completo
rechazó dos pruebas porque el nuevo registro se había colocado después del
arranque de la CLI directa. Se corrigió el orden sin quitar o suavizar esas
pruebas. Los recibos rechazados y la corrección se conservan como intento 1.

La versión corregida pasó 2,799 pruebas, incluidas las 2,770 anteriores en
sus mismos grupos. La CLI de comportamiento creó y verificó el expediente en
procesos separados. El resultado conserva 42 eventos y 18 usos, 11 permitidos
y siete rechazados. La aceptación y sus límites de digest figuran en
`CONTINUATION.md`; la ejecución nativa histórica no convierte este perfil de
modelo en un perfil nativo.
