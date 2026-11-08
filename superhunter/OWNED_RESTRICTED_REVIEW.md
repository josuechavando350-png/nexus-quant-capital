# Revisión propia con cómputo restringido

`check-owned-restricted-boundary` ejecuta cinco ensayos reales sobre una copia
temporal propia: baseline, archivo fijo ausente, restauración, modo cambiado y
restauración. El worker es `owned_restricted_worker.py`; no admite destinos ni
comandos. Los archivos copiados se leen como datos, nunca se ejecutan.

```bash
python -B -m superhunter check-owned-restricted-boundary \
  --source-digest DIGEST --out SALIDA_NUEVA
python -B -m superhunter verify-owned-restricted-boundary \
  --source-digest DIGEST --bundle SALIDA_NUEVA --experiment-anchor ANCLA
```

La salida debe estar fuera del repositorio y ser nueva. La verificación requiere
los bytes de la fuente/productor que corresponden a ese expediente. Este perfil
no cambia el significado de los expedientes anteriores de captura o diagnóstico.

## Fases y límites

| Fase | Comportamiento comprobado |
| --- | --- |
| Padre | Captura fuente e inventario; crea copia privada con el ciclo de vida de PR105 |
| Adquisición del hijo | Lee la copia dos veces, compara bytes/modos, carga módulos y biblioteca fijada |
| Instalación | Comprueba un solo hilo, solo FD 0/1/2, entrada `/dev/null`, salidas regulares o pipes |
| Cómputo | Aplica seccomp con denegación por defecto; calcula la política sobre bytes en memoria |
| Cierre del padre | Comprueba que la copia y el marcador siguen iguales, conserva cada salida y limpia |
| Revisión posterior | Recalcula coherencia, hashes, tiempos, controles y resultado; no reejecuta el filtro |

CPU del hijo: 15 s. Memoria virtual: 256 MiB. Archivo durante carga: 128 KiB;
después de cargar la biblioteca se reducen los límites blando y duro a 64 KiB.
El padre admite hasta 64 KiB por stream y espera hasta 30 s por ensayo. Estos
son límites por proceso/archivo; no se afirma un presupuesto agregado de host.

La biblioteca libseccomp conserva el pin ya existente:
`b4d9140a7797ccf3ac14f5d9d579b64f157111662940cb8330c632b11a8cea8e`,
125,360 bytes, cargados desde un memfd sellado. No se instala otra dependencia.

## Política aplicada

La política deniega llamadas por defecto con EPERM y permite una lista corta
de memoria, señales, reloj, terminación y operación sobre stdio. Las lecturas
solo se permiten desde FD 0 y las escrituras desde FD 1/2. No se permiten nuevas
aperturas, duplicación de descriptores, sockets ni creación de procesos. Los
mapeos nuevos deben ser anónimos, con FD -1 y sin PROT_EXEC; mprotect no puede
añadir PROT_EXEC. Los argumentos y el digest de las reglas forman parte del
perfil comprobado. La política se instala únicamente en un hijo dedicado.

Los controles propios de lectura, apertura de escritura y directorio deben
funcionar antes de instalar el filtro, y fallar con EPERM después. Para sockets
se conserva la disponibilidad previa por familia: AVAILABLE o ALREADY_DENIED_EPERM.
Un rechazo preexistente no se atribuye al nuevo filtro. Nunca se conecta a una
dirección, se abre un listener ni se envía un paquete en esos controles.

Los tests nativos comprueban además un mapeo anónimo legible/escribible y el
rechazo de variantes de mapeo, PROT_EXEC, duplicación de FD y archivo nuevo.
La prueba de descriptor heredado introduce deliberadamente un FD propio en un
hijo real; no simula el retorno del filtro. El productor conserva el fallo y
no continúa con restauraciones que pudieran ocultarlo.

## Resultado y límites de interpretación

Solo cinco resultados completos y coincidentes producen OWNED_RESTRICTED_LAB_PASS.
Timeout, filtro no disponible, salida inesperada o control incompleto producen
INCONCLUSIVE. La adquisición se detiene en el primer resultado inesperado y no
hay cálculo alternativo sin el filtro. Un expediente manipulado que intenta
mantener un PASS se rechaza al reconstruir el resultado.

Los relojes de adquisición, filtro y cómputo del hijo deben estar ordenados y
dentro del intervalo observado por el padre. El inventario declarado por el
hijo debe coincidir con el comprobado por el padre antes y después. La identidad
del worker es la nueva; no se reasigna la identidad del worker histórico.

La adquisición de archivos y la carga de módulos ocurren **antes** del filtro.
Bibliotecas y datos previamente mapeados siguen en memoria. No se acredita
integridad de memoria, ejecución independiente, host confiable, aislamiento de
código hostil o un sandbox general. La documentación del kernel distingue el
[filtrado de syscalls de un sandbox completo](https://www.kernel.org/doc/html/next/userspace-api/seccomp_filter.html).
Las [comparaciones de argumentos de libseccomp](https://man7.org/linux/man-pages/man3/seccomp_rule_add.3.html)
se usan para delimitar descriptores y memoria; no comprueban punteros o rutas.

Los dos fallos de integridad son controles declarados, no descubrimientos de
vulnerabilidades. No se crean nuevos findings ni planes de reparación y no se
modifican destinos externos. M1 sigue parcial. Los estados de los catálogos y
las aceptaciones nativas EVM/Slither anteriores mantienen sus propios límites.

## Fallos encontrados durante la integración

El primer prototipo exigía que ambos tipos de socket estuvieran disponibles;
el entorno ya bloqueaba uno. Se corrigió el registro para conservar ese estado
previo. Después, la prueba real del worker detectó que el límite de archivo de
64 KiB impedía escribir la biblioteca de 125,360 bytes en su memfd. Se separó la
carga acotada de 128 KiB y el límite posterior de 64 KiB. Los intentos fallidos
se conservan y no se contabilizan como ejecuciones exitosas.

Las corridas completas y el digest aceptado se registran en CONTINUATION.

## Evaluación de QA dentro de los presupuestos existentes

La primera corrida integral alcanzó el límite de CPU del grupo 5. Una
redistribución experimental conservó todas las pruebas, pero el grupo 7 también
alcanzó su límite: su módulo de revisión compartida consumía por sí solo más de
90 segundos de CPU en la medición instrumentada. Ambas corridas bloqueadas se
conservan; no acreditan QA completo.

La versión final conserva los grupos históricos y elimina un recorrido repetido
en `quality.assess`. Un índice temporal asigna cada fila a sus componentes por
prefijo, preservando orden, duplicados, propietarios compartidos y prefijos
generales. No guarda resultados entre llamadas ni reutiliza aprobaciones o
fuentes. Las pruebas obligatorias se consultan en el mismo conjunto de IDs ya
validado; no se omite ninguna condición del gate.

Cinco regresiones contrastan el índice con una referencia de prefijos directa.
Una comparación adicional usa recibos explícitamente sintéticos: nueve casos
conservan resultado/error idéntico y doce pares alternados miden el mismo cálculo.
Su mediana de CPU pasó de 102.725 ms a 2.997 ms. Esto caracteriza esa entrada y
función en este host; los PASS inventados de ese fixture no son ejecución de
pruebas ni una medida general de rendimiento de Hunter.

También se corrige la admisión del temporal: si la ruta se reemplaza antes de
abrirla, se cierra el descriptor efectivamente adquirido y se conserva la ruta
reemplazada. Cuatro regresiones nuevas cubren directorio, enlace, ausencia y
archivo regular. Los informes inconclusos describen requisitos de aceptación;
no afirman controles completados cuando no hay una respuesta coincidente.
