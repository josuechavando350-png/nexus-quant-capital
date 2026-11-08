# Contrato correcto y contra-controles en dos EVM

Perfil separado: `owned-correct-counter-controls-two-evm-cancun-v1`.
Ejecuta únicamente la fuente Solidity correcta del laboratorio existente,
sobre los 16 casos fijos del corpus de contra-controles. La entrada no puede
seleccionar otra variante, fuente, contrato, dirección, red o programa externo.
Los perfiles históricos y sus métricas quedan separados y sin modificaciones.

## Qué se contrasta

Se conserva la fuente correcta `OwnedAuthority` y su compilador fijado,
con las dos configuraciones existentes (`legacy` e `ir_optimized`). Cada
configuración procesa todos los casos desde un constructor nuevo. Los motores
son el CLI EVM fijado de Geth y la implementación Cancun fijada de EELS.

El inventario exigido por motor es de dos compilaciones, 32 constructores y
116 llamadas. De estas, 32 son sondas de un gas antes del primer uso de cada
secuencia. Las sondas deben fallar sin persistir cambios. El siguiente intento
con gas suficiente debe ejecutar el evento una sola vez. Son 16 casos
conocidos y 13 secuencias distintas, no 64 muestras independientes.

El comparador exige igualdad de compilaciones, runtime del constructor,
estado inicial, estados antes/después, retorno y estado de ejecución.
Las proyecciones se contrastan con las 42 observaciones escritas y el modelo
correcto: 11 usos aceptados y siete rechazados. Una consulta de historial
comprueba también la máscara de permisos y las ocho generaciones en cada
paso, incluidos los ámbitos que deben permanecer intactos.

Un uso rechazado puede ser una llamada EVM `COMMITTED` que devuelve `false`.
Ambos estados se conservan por separado. Los decodificadores existentes
usan operaciones distintas: desplazamientos de bits y cortes de bytes.
No se comparan costos de gas ni raíces globales de cuentas.

## Alcance del contrato

Es una máquina abstracta, no un servicio de autorización. Grant/revoke son
comandos confiables del escenario. Los principales son bits del comando,
no `msg.sender`, firmas o credenciales autenticadas. El contrato no se
publica, despliega ni conecta a una red por estos comandos de laboratorio.

Este perfil no ejecuta variantes defectuosas ni detectores y no calcula
TP/TN/FP/FN. La omisión `latent_revocation` del perfil histórico sigue
existiendo. Los resultados del perfil nuevo no corrigen retroactivamente esa
omisión ni se suman a su denominador.

## Repetición y límites

La creación escribe observaciones de ambos motores, proyecciones, informe y
manifiesto en un directorio nuevo fuera del checkout. El verificador requiere
los binarios fijados, repite ambos motores y compara los artefactos completos.
Si no puede repetirlos, falla; no sustituye la repetición por hashes guardados.
Al terminar revalida el inventario de evidencia, sus bytes y las fuentes.

```sh
python3 -B -m superhunter compare-owned-correct-engines --solc /privado/solc --evm /privado/evm --expected-source DIGEST_ESPERADO --out /privado/correcto-dos-evm
python3 -B -m superhunter verify-owned-correct-engines --solc /privado/solc --evm /privado/evm --expected-source DIGEST_ESPERADO --bundle /privado/correcto-dos-evm
```

Se heredan los transportes cerrados y presupuestos existentes: cada worker
usa 180 s de pared, 90 s de CPU, 2 GiB de espacio de direcciones y 20 MiB por
archivo. La imagen fijada de Geth se prepara antes del límite del hijo,
mediante el transporte existente de imagen sellada. No se aumentan esos
límites ni se habilitan workflows.

Los motores comparten compilador, entradas, host y política. La coincidencia
no autentica productores independientes ni prueba integridad de memoria,
aislamiento completo del host o toda la semántica EVM. El comparador de
objetos por sí solo puede recibir objetos fabricados; la evidencia nativa
requiere crear y repetir el perfil mediante sus workers reales.

Las regresiones unitarias usan observaciones **sintéticas**, expresamente
rotuladas. Sus PASS no acreditan ejecución nativa. Los resultados nativos y
QA correspondientes a cada digest se registran en `CONTINUATION.md` solo
cuando se ejecutan. No hay afirmación de vulnerabilidad original, producción,
operación 24/7, integración de 50 proyectos ni porcentaje global completado.


## Validación de esta entrega

36 pruebas focalizadas PASS, incluidas 34 nuevas y las dos regresiones de
paridad entre entradas CLI. El primer pase focal falló dos pruebas por una
referencia al nombre de componente incorrecto; se corrigió al componente
existente `owned_authority_evm`. Ambos registros se conservaron. Las pruebas
unitarias usan recibos sintéticos y se separan de la aceptación nativa real.

El perfil se creó y verificó con Geth/EELS reales en procesos separados, tanto
en la copia preliminar como en el checkout integrado, cuyos bytes ejecutables
coinciden exactamente. Cada motor cumplió las dos compilaciones, 32
constructores y 116 llamadas exigidas, incluidas las 32 sondas. El estado y
las decisiones coincidieron con las expectativas del modelo correcto.

QA completo con SDK real: 2,833 PASS, cero fallos/errores/skips; 2,799 pruebas
anteriores conservadas en sus grupos y 34 nuevas. Se verificaron QA, telemetría
y preparación desde un proceso sin SDK. Ocho workers y límites intactos;
máximo observado 81.162 s. La aceptación histórica Slither/Geth/EELS también
se repitió sobre este digest, preservando su omisión conocida y denominadores.
Los detalles, límites y archivo de evidencia están en `CONTINUATION.md`.
