# Propiedades Solidity con consultas nativas y Z3

Este laboratorio es **fijo y local**. No descubre objetivos, no admite contratos
externos, no produce exploits y no ejecuta una EVM. No sustituye las integraciones
pendientes de Foundry, Slither ni los conectores de plataformas.

## Cambio funcional

El binario oficial de solc suministrado está fijado por el mismo SHA-256 que usa
native_compile. Este binario no expone un solver Z3 integrado utilizable en este
entorno. Se comprobó su aviso de solver no disponible; no se interpretó como una
propiedad segura.

La ruta nueva utiliza el intercambio SMT-LIB2 del compilador: solc transforma
fuentes Solidity propias en consultas; la biblioteca Z3 instalada las resuelve;
las respuestas se devuelven a solc mediante auxiliaryInput.smtlib2responses.
El compilador debe emitir un diagnóstico explícito para la posición exacta de
la aserción y dejar cero consultas pendientes. Ausencia de warnings no es prueba.

Los comandos son:

```bash
python3 -m superhunter prove-solidity-controls \
  --binary /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --out /ruta/privada/caso-nuevo

python3 -m superhunter replay-solidity-controls \
  --binary /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --bundle /ruta/privada/caso-nuevo
```

El único perfil alternativo es `--budget exhausted`: impone un límite Z3 de un
recurso y comprueba que UNKNOWN no se convierta en UNSAT. Es un control de límite,
no una configuración útil para investigación. Se aplica tanto a creación como
replay; el verificador exige el presupuesto esperado explícito o el normal por
defecto. No existen argumentos --source, --target, --query o --rpc.

## Controles y especificación

La fuente fija calcula la transferencia aritmética de una cantidad entre dos
números pequeños, sin tokens, direcciones, storage ni llamadas externas. Las
entradas son uint8 y los guards restringen los saldos a 0..15 y la cantidad al
saldo de origen. El dominio de 16^3 contiene 4,096 tuplas; 2,176 satisfacen los
guards. Los resultados intermedios usan uint16 y no se desbordan en ese dominio.

1. conservation: los cambios de ambos saldos conservan el total.
2. off_by_one: el mismo código suma una unidad adicional al destino. Cambia solo
   un literal; conserva dominio y aserción. Z3 produce un contraejemplo.
3. unreachable: require(false) vuelve imposible la ruta. UNSAT no se presenta
   como seguridad: se etiqueta VACUOUS_NO_CERTIFICATION.

Para cada control se compila también un probe de factibilidad que mantiene el
cuerpo y guards, pero cambia la última aserción a assert(false). SAT demuestra
que hay al menos una entrada que alcanza ese punto dentro del modelo. Un solver
que devuelve UNKNOWN en el control normal deja FORMAL_INCONCLUSIVE aunque la
referencia enumerada haya terminado sin errores.

Una referencia Python enumera el dominio conocido. Todo testigo SAT se convierte
en números y se comprueban guards, operaciones, resultados y violación real de
la aserción del control. Un desacuerdo bloquea el resultado. Esto contrasta el
modelo de estos ejemplos; NO es ejecución de bytecode ni un compilador separado.

## Integración

CLI -> native_compile (binario sellado y límites existentes) -> consultas de
solc -> smt_backend (Z3 C API) -> respuesta consumida por solc -> referencia
concreta -> AuditLog nativo DIABLO -> paquete verificable. El componente está en
quality.COMPONENTS y tiene pruebas obligatorias; sus imports aparecen en el grafo.

review-platform sigue ejecutando la suite del paquete y sus controles habituales.
**No obtiene el binario ni ejecuta automáticamente este laboratorio nativo.** La
aceptación nativa se ejecuta por los dos comandos anteriores y se registra aparte.
Las pruebas unitarias con capturas/mocks no se cuentan como compilaciones nuevas.

El paquete contiene inputs exactos, salidas iniciales/finales originales, consultas,
respuestas y límites de Z3, versión/hash de la biblioteca, hash del compilador,
identidad del código, decisión y auditoría. Los originales no se editan.

El replay NO ejecuta consultas leídas del paquete: reconstruye las fuentes fijas,
vuelve a compilar y resolver, y compara todos los artefactos esperados. La fecha
de producción se conserva como atributo no autenticado. Un manifiesto recalculado
no sustituye la reproducción. Se usan los mismos motores y versiones; no es
verificación por dos implementaciones ni verificación de un certificado UNSAT.

## Requisitos y límites

Linux x86-64, el binario oficial solc 0.8.30 ya aportado y la biblioteca nativa
Z3 disponible en las rutas admitidas por smt_backend. No instala ni descarga nada.
Cada query tiene timeout de 3,000 ms y límite de recursos; el compilador conserva
sus límites de CPU/memoria/salida y ausencia de callback de importaciones.
La biblioteca Z3 es código nativo confiado, NO un sandbox para código hostil.

El perfil es BMC de funciones puras conocidas, sin loops, herencia ni estado.
No se certifica todo Solidity, upgrades, ausencia universal de fallos, autorización
externa o recompensas. El benchmark es conocido, no ciego. No hay vulnerabilidad
nueva de terceros, transacción, firma de fondos, RPC ni operación 24/7.

Referencias de interfaz utilizadas:
- https://docs.soliditylang.org/en/v0.8.30/smtchecker.html
- https://github.com/argotorg/solidity/blob/v0.8.30/libsolidity/interface/StandardCompiler.cpp
- https://z3prover.github.io/api/html/group__capi.html
