# Aceptación integral con entornos separados

**Consumidor posterior:** [OWNED_DEFENSIVE_ACCEPTANCE.md](OWNED_DEFENSIVE_ACCEPTANCE.md) exige este perfil de cuotas junto con autoridad temporal nativa y el mismo digest de QA. Sus denominadores se mantienen separados y la omisión conocida no se elimina.

Perfil: `whole-qa-and-owned-quota-two-environments-v1`.

El entorno QA exige Linux x86_64, Python 3.12 con memfd y F_ADD_SEALS,
PyYAML 6.0.3, cryptography 46.0.4 y la biblioteca Z3 histórica con SHA256
`7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0`.
El entorno EELS conserva sus 23 dependencias y hashes fijados, incluido
cryptography 45.0.7. No se sustituyen versiones para fingir que un entorno
satisface ambos contratos.

## Recorrido

Desde el checkout publicado, con salidas privadas nuevas fuera del código:

```bash
/ruta/qa-venv/bin/python -B -m superhunter prepare-owned-platform --out /evidencia/preparada
/ruta/eels-venv/bin/python -B -m superhunter verify-owned-preparation --bundle /evidencia/preparada --expected-source SHA256_DEL_CODIGO
/ruta/eels-venv/bin/python -B -m superhunter finish-owned-platform --prepared /evidencia/preparada --out /evidencia/integral --solc /herramientas/solc --evm /herramientas/evm --expected-source SHA256_DEL_CODIGO
/ruta/eels-venv/bin/python -B -m superhunter verify-owned-platform --bundle /evidencia/integral --solc /herramientas/solc --evm /herramientas/evm --expected-source SHA256_DEL_CODIGO
```

El digest esperado debe provenir del código publicado y revisado, no confiarse
únicamente al informe recibido. `prepare` ejecuta toda la QA y los controles
locales existentes; solo después escribe `readiness/COMPLETE.json`.
`finish` verifica esa preparación, copia únicamente sus archivos inventariados,
ejecuta los seis casos propios en Geth/EELS y exige otra ejecución de ambos
motores antes de escribir `review/COMPLETE.json`. El resultado final es autónomo:
no necesita conservar la carpeta original de preparación.

El último comando se ejecuta en otro proceso. Revalida los recibos completos de
QA sin volver a ejecutar sus tests, recompila los contratos propios, repite los
motores y compara todos los bytes esperados. Comprueba el código antes y después,
inventarios cerrados, hashes, marcadores, ausencia de enlaces simbólicos y
límites de tamaño. Un fallo o interrupción deja una salida parcial sin aceptación.
Ni la preparación ni la salida final se sobrescriben; se requiere otra carpeta.

## Alcance de los controles

Se conservan los cinco controles numéricos, 256 casos de fuzz numérico,
tres casos contables, ocho de permisos y cuatro de secuencias del perfil local.
La etapa nativa usa seis variantes conocidas de cuotas, con cuatro defectos
sembrados y dos controles correctos. Registra verdaderos/falsos positivos y
negativos, además de las omisiones al retirar dimensiones del detector.
Los doce constructores y 228 llamadas por motor son observaciones de esos
mismos seis casos; no son casos nuevos ni una evaluación ciega.

Los ocho trabajadores QA se ejecutan secuencialmente, cada uno con 180 s de
pared, 90 s CPU, 2 GiB de espacio de direcciones y 20 MiB por archivo.
Los trabajadores de comparación conservan 180 s de pared, 90 s CPU y 2 GiB;
sus hijos Geth tienen límites más estrictos de CPU/salida. El padre prepara la
imagen Geth de 42,001,080 bytes en memoria sellada antes de iniciar el trabajador
con su límite de archivos. No se afirma un límite agregado de todo el árbol de
procesos ni una certificación de aislamiento del sistema operativo.

Los tests de orquestación usan dobles explícitos de QA y motores: prueban rechazos
y secuenciación, no ejecuciones EVM. La aceptación real requiere los comandos
anteriores con los binarios y dependencias fijados.

## Límites de la evidencia

El registro de preparación acredita coherencia con recibos y fuentes actuales;
no autentica a un productor remoto. Una colección de hashes recalculados no
demuestra por sí sola que un tercero ejecutó QA. Las dos EVM comparten compilador,
fuentes, entradas, host y detector. No se certifican todas sus semánticas, costes
de gas, raíces de cuentas, generalización ni independencia de productores.

El perfil nativo histórico, sus tres contratos y sus capturas quedan intactos.
Este perfil nuevo no los recertifica bajo otros límites. Se conservan los
catálogos de 27 integraciones, 50 capacidades y 25 iniciativas sin reclasificarlos.
No se aceptan objetivos, contratos o calldata externos ni RPC, intérpretes,
firmas o transacciones. Plataforma completa: no. Vulnerabilidades originales
confirmadas: ninguna por esta prueba. Avance global no determinado.
