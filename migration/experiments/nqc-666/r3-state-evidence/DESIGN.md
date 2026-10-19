# NQC666 R3 — evidencia antes de decisión

## Frontera de confianza

`Policy` se configura fuera del paquete recibido. Fija cadena declarada, altura,
hash y timestamp del encabezado, cuenta, hash de código, mercado, prestatario,
vigencia y versión del layout. El paquete no elige sus propios parámetros de
aceptación. Cambiar esa política requiere una decisión del llamador de confianza;
R3 no descubre ni selecciona automáticamente la cadena canónica.

Una prueba válida demuestra que unos bytes pertenecen a la raíz de un encabezado
fijado. **No demuestra que ese encabezado sea canónico o finalizado.** El chain ID
no está autenticado por los campos del encabezado Ethereum aquí utilizados.
`canonicality` siempre se entrega como `unknown`. `historical_observation` expresa
procedencia documental; no es una certificación de consenso. El único otro origen
aceptado es `synthetic_fixture`.

El hash del código autentica bytes de código bajo esa misma raíz. El pin del hash
y el nombre de un layout tampoco prueban por sí mismos que el código sea una
compilación concreta de Morpho. El resultado marca
`layout_assurance=explicit_policy_assumption`. El corpus deliberadamente usa código
sintético distinto de Morpho; no se le atribuye ejecución del protocolo real.

## Comprobaciones implementadas

1. Bytes JSON limitados a 2 MiB; claves duplicadas y constantes no JSON rechazadas.
   Se acepta un subconjunto estricto de hex RPC: minúsculas, cantidades sin ceros
   iniciales, datos con número par de dígitos y anchos explícitos. No se reparan
   silenciosamente paquetes ambiguos.
2. Esquema exacto de sobre/cuenta/slots. Solo estado al final de un bloque;
   ningún preestado de una transacción se infiere desde ese estado.
3. Encabezado de 21 campos, incluyendo `requestsHash`, como el fixture histórico
   recuperado. Se reconstruye su RLP y Keccak y se exige coincidencia con el pin.
   No es un verificador universal de todas las bifurcaciones de Ethereum. Campos
   JSON auxiliares del RPC no forman parte de esa autenticación.
4. Prueba de cuenta con clave `keccak(address)`: cuenta existente, RLP de cuatro
   componentes, enteros mínimos, coincidencia de nonce, saldo, raíz de almacenamiento
   y hash de código. El código recibido debe coincidir con el hash fijado.
5. Nueve slots de Morpho: posición (`borrowShares`, `collateral`), tres palabras
   del mercado y cinco parámetros. Cada clave usa `keccak(slot de 32 bytes)`.
   Se exige cobertura exacta, sin duplicados, extras ni datos sustituidos.
6. Pruebas de inclusión y ausencia. Una ausencia demostrada vale cero; una prueba
   faltante se rechaza. Cero almacenado mediante una codificación no canónica se
   rechaza. No se acepta metadata RPC si difiere del valor demostrado.
7. Nodos RLP acotados, rutas compactas y referencias de hijos comprobadas; el recorrido
   utiliza `trie 4.0.0`. Se rechazan nodos repetidos o ajenos a la ruta. El orden de los
   nodos no aporta autoridad. Límites: 65 nodos por prueba y 2.048 bytes por nodo.
8. ID del mercado recalculado desde sus cinco parámetros; padding de direcciones,
   LLTV, tiempo/fee del mercado, shares de la posición y relación deuda/suministro
   comprobados. Las palabras originales se conservan en una tupla inmutable.

Las bibliotecas Keccak, RLP y trie ya estaban instaladas para R1. No se añadió una
implementación criptográfica propia para perseguir nanosegundos. La tabla por
paquete reutiliza únicamente la decodificación y validación de nodos idénticos;
cada ruta vuelve a comprobarse contra su raíz y clave. No persiste caché entre bloques.

## Gateway, invalidación e integración R1

`Gateway` tiene un solo hilo propietario. Cada ingreso invalida el snapshot anterior
**antes** de parsear o verificar el nuevo. Un error deja el gateway sin hechos
utilizables. Reset de política, cambio de bloque o reorganización declarada cambian
la época y eliminan el snapshot. Los tickets verifican época, hash, reloj local y
vigencia. Un ticket inválido también borra el snapshot actual: es una decisión
conservadora, con posible coste de disponibilidad. No hay recuperación tácita de
un candidato antiguo tras un error.

El llamador suministra `now_s`; debe ser un reloj confiable. Se rechazan retrocesos
observados, pero el módulo no puede detectar que un llamador congele deliberadamente
el reloj o suplante la política. El watermark local se conserva tras un reset.
No se prometen seguridad entre hilos, persistencia tras reinicios ni resistencia
a un proceso de confianza comprometido.

`scenario` conecta los campos verificados al ejecutable Rust R1 **sin modificarlo**,
por stdin/stdout local. Solo prepara un cálculo condicional si el mercado ya tiene
`lastUpdate == timestamp del bloque`. Si falta acumulación de intereses, devuelve
error y borra el snapshot. No se ha ejecutado el IRM ni el oráculo.

El precio entregado a `scenario` es un **supuesto explícito**. La salida se denomina
`conditional_prediction_not_observed_eligibility`; nunca se convierte en elegibilidad
observada. Las pruebas contrastan deuda, capacidad y desigualdad de liquidación con
aritmética entera independiente. El proceso Rust es una dependencia local de confianza,
ya compilada e iniciada; el IPC no es una frontera autenticada entre máquinas.

`authorize` siempre devuelve `commercial_admission=False` y `observed_candidate=None`.
Esta es una puerta de investigación cerrada, no una sustitución del guardián económico
original. No se conecta a la selección comercial de R2 ni ejecuta en este camino sus
comprobaciones completas de financiación/pagos. Esos módulos y sus fuentes permanecen
intactos. Ninguna prueba sintética habilita ejecución comercial.

## Qué integra realmente esta revisión

| Componente | Evidencia y comportamiento |
|---|---|
| Cerebro de estado / guardián de integridad | Verificación relativa a raíz fijada de cuenta, código y nueve slots |
| Cerebro económico | Reutiliza las fórmulas exactas R1 para escenarios explícitos |
| Tercer Ojo | Separa hechos relativos a raíz, supuestos y predicción condicional; deuda no acumulada queda desconocida |
| Coordinación | Épocas/tickets, invalidación previa al fallo, reloj y reset secuenciales |
| Cazadores / prioridad comercial | No reciben una oportunidad observada con evidencia incompleta |
| Guardianes financieros y de ejecución | Continúan pendientes como autorizaciones externas; el ingreso no los suplanta |

No se crean 18 servicios, agentes adicionales ni concurrencia de búsqueda. El worker
Rust es una integración de laboratorio para comprobar reutilización de R1 y medir su
IPC; no se recomienda añadir ese salto de proceso al futuro camino crítico.

## Evidencia y límites

- 16 testigos sintéticos, con raíces comprobadas por un constructor batch independiente
  de `py-trie`. Ambos comparten Keccak y RLP, por lo que no es independencia criptográfica
  total. El corpus modela profundidad/cobertura de pruebas; no es una distribución real
  observada de Morpho.
- 514 pares mercado/prestatario contrastados contra los nueve getters de
  `MorphoStorageLib` del commit upstream fijado. Se ejecuta un harness puro en una EVM
  local en memoria; no es un despliegue, una simulación completa de Morpho ni un fork.
- Un encabezado histórico real recuperado, byte a byte, de una rama técnica de NQC.
  Su hash se valida. No se dispone de su paquete completo de pruebas Morpho; el camino
  de estado permanece bloqueado. No se efectuaron consultas RPC nuevas.
- El inventario cubre las cuatro ramas y búsquedas registradas en `PROVENANCE.json`.
  No afirma demostrar ausencia global de testigos en todos los archivos/repositorios.
- Pruebas adversariales de mutación, metadata, identidad, rutas, ceros, límites de
  parsing, obsolescencia, reorganización e integración condicional. No son una auditoría
  formal, una demostración exhaustiva ni una prueba de disponibilidad de producción.

## Continuación técnica

El siguiente avance requiere un paquete real reproducible con cuenta, código y slots,
una política independiente de anclaje de cadena y la ejecución verificable de oráculo/
IRM sobre un estado coherente. Una prueba del contrato Morpho por sí sola no autentica
el resultado de llamadas a contratos externos. Tampoco reconstruye el preestado de una
transacción dentro del bloque. No se fabrica ese material ni se extrapola del fixture.

Cuando exista, conviene verificar la evidencia por evento/snapshot y entregar hechos
tipados inmutables al motor residente en Rust. La validación de época, identidad y
vigencia debe seguir en cada decisión final. No se propone eliminar la autenticación
para cumplir 700 ns, y 5 ns sigue restringido al filtro mínimo preparado experimental.
Una eventual implementación Rust del verificador debe utilizar primitivas mantenidas
y reproducir el corpus completo; aquí no se presume una mejora sin medirla.

Fuentes primarias: [EIP-1186](https://eips.ethereum.org/EIPS/eip-1186),
[EIP-1898](https://eips.ethereum.org/EIPS/eip-1898),
[trie Patricia de Ethereum](https://ethereum.org/developers/docs/data-structures-and-encoding/patricia-merkle-trie/),
[MorphoStorageLib fijada](https://github.com/morpho-org/morpho-blue/blob/9cf6d5b844625ba108e36d1cf911f5d2faf7c136/src/libraries/periphery/MorphoStorageLib.sol).
