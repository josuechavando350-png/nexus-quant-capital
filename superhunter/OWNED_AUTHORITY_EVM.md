# Corroboración EVM de permisos temporales propios

Perfil cerrado `owned-temporal-authority-two-evm-cancun-v1`: solo los once casos
conocidos de `OWNED_AUTHORITY.md`. No admite contratos, direcciones, RPC, código,
datos de terceros o secuencias suministradas por CLI. Los principales son bits
en un modelo abstracto, no identidades autenticadas mediante `msg.sender`.
Las órdenes de concesión y revocación se consideran confiables dentro del
laboratorio. Este contrato no es un servicio de autenticación para producción.

## Evidencia de ejecución

Se compilan siete variantes con dos modos de solc: catorce compilaciones por
implementación. Cada caso y modo comienza con una instancia vacía: veintidós
constructores. Las 42 observaciones lógicas se ejecutan en cada modo, junto con
una sonda de un gas por instancia: 106 llamadas por motor, incluidas 22 sondas.
Una sonda fallida debe conservar íntegro el estado; el reintento normal consume
el evento una sola vez. No se envían transacciones a una cadena o servicio.

Geth y EELS deben coincidir en bytecode construido, estado inicial, estado
persistido completo, resultado y retorno. Se usan decodificadores distintos
de la palabra de almacenamiento: máscaras de bits y cortes de bytes. La
proyección a observaciones abstractas debe coincidir también con el modelo
Python publicado. Las dos EVM comparten compilador, entradas, host y política;
no prueban independencia de productores ni certifican toda la semántica EVM.
No se comparan costes de gas ni raíces del estado de cuentas.

## La aplicación puede rechazar una llamada que la máquina ejecuta

`step` devuelve un booleano y conserva el mismo valor en `accepted`. Una
llamada que devuelve `false` puede terminar `COMMITTED`. El detector consume
el valor de aplicación; usar solo el éxito de la máquina altera las decisiones.
Una ablación deliberada cuantifica ese error de interpretación.

La expectativa del corpus conocido es TP6/TN4/FP0/FN1 con el detector completo.
La omisión `latent_revocation` se conserva: su secuencia no revoca y su traza
coincide con `clean_repeat`. La ablación que equipara éxito EVM y autorización
espera TP6/TN1/FP3/FN1. Estas expectativas se aceptan únicamente tras ejecución;
los tests unitarios con observaciones sintéticas no sustituyen los motores.
Las llamadas, compilaciones y repeticiones no añaden muestras independientes.

## Ejecución acotada

En el entorno EELS separado, con sus 23 dependencias exactas y los binarios
solc/Geth publicados y fijados por hash, desde el checkout revisado:

```bash
python -B -m superhunter compare-owned-authority-engines --solc /herramientas/solc --evm /herramientas/evm --expected-source DIGEST --out /evidencia/autoridad
python -B -m superhunter verify-owned-authority-engines --solc /herramientas/solc --evm /herramientas/evm --expected-source DIGEST --bundle /evidencia/autoridad
```

El verificador debe ejecutarse en otro proceso. Recompila y repite ambos motores,
recalcula métricas y compara los artefactos completos, inventario cerrado y
marcador final byte por byte. Un fallo deja la evaluación bloqueada; no se
convierte en resultado negativo del detector. El código cero significa que
la evaluación y comparación terminaron, aunque el resultado conserva FN1.

Cada trabajador exterior mantiene 180 s de pared, 90 s CPU, 2 GiB y 20 MiB
por archivo. El padre prepara en memoria sellada la imagen Geth oficial de
42,001,080 bytes antes de pasar al trabajador. El transporte existente conserva
15 s por ejecución, 10 s CPU y 2,000,000 bytes de salida del proceso Geth. No se
modifican límites, capturas, compilador o motores históricos. Son límites por
proceso; no aislamiento de código hostil ni presupuesto agregado del host.

La QA completa mantiene sus ocho trabajadores y el entorno separado con PyYAML
6.0.3, cryptography 46.0.4 y Z3 exacto. El perfil integral de cuotas existente
continúa siendo una evidencia distinta; no se atribuye autoridad temporal a ese
perfil hasta que un consumidor lo exija explícitamente.

Sin firmas, fondos, credenciales reales, objetivos externos ni descubrimientos
originales. Plataforma completa: no. Avance global no determinado.
