# Controles Solidity con estado persistente — CHC

Implementación defensiva y local. Solo admite tres fuentes propias incluidas en
`solidity_stateful.py`, no objetivos, contratos externos, SMT aportado, ni
código de entrada. No hay llamadas RPC, firma, despliegue o explotación.

## Lo que ejecuta

El binario oficial solc 0.8.30, comprobado por el driver existente, genera
cláusulas Horn desde un contrato con tres variables persistentes. La biblioteca
Z3 instalada resuelve las consultas emitidas, y el mismo compilador consume
sus respuestas. El diagnóstico debe corresponder a la aserción exacta.
El verificador repite este recorrido, no acepta una firma o un hash como
sustituto de ejecución. DIABLO registra los resultados y la identidad del código.

En este perfil HORN, SAT indica que las cláusulas que excluyen el fallo son
satisfacibles (aserción SAFE), y UNSAT indica VIOLATED. Es la polaridad inversa
a la consulta BMC anterior que buscaba una entrada incumplidora. Se contrasta
explícitamente con los diagnósticos de solc y con dos referencias concretas.

## Controles y cobertura

Estado inicial: debit=15, credit=0, steps=0. La función admite quantity cuando
steps<3 y quantity<=debit. Una cantidad nula está permitida explícitamente.
La variante correcta conserva el total. La variante alterada crea una unidad
solo en la tercera operación. La variante inalcanzable usa require(false).
Las versiones alcanzables difieren solamente en un literal, 0 frente a 1.

Se comprueba separadamente si la tercera aserción es alcanzable. Un diagnóstico
favorable detrás de una precondición imposible no produce certificación. Un
resultado UNKNOWN siempre deja el caso inconcluso, incluido el control imposible.

La referencia por grafo utiliza transiciones concretas; la segunda enumera
las 4,096 tuplas de cantidades 0..15 y calcula balances con sumas de prefijos.
Ese dominio cubre las cantidades admisibles: debit comienza en 15, nunca aumenta,
y cualquier uint8 mayor que 15 falla el guard en todo estado alcanzable.
Hay 816 secuencias de tres cantidades que cumplen los guards en cada variante
alcanzable. Las 816 violan el total en la versión alterada, en la tercera operación.

**Los estados de referencia se observan en el punto de la aserción, antes de un
posible revert.** Una secuencia que llega a una aserción falsa no es una secuencia
de transacciones completadas o de estados confirmados en una cadena. No se modelan
gas, receipts, bytecode, commits de estado ni rollback de una EVM. El contraejemplo
concreto proviene de la referencia finita, no de una traza CHC extraída ni de EVM.

## Uso desde la raíz del paquete

```bash
python3 -m superhunter prove-stateful-controls \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --out /ruta/privada/nuevo
python3 -m superhunter replay-stateful-controls \
  --solc /ruta/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --bundle /ruta/privada/nuevo
```

`--budget exhausted` usa un presupuesto real de un recurso de Z3. Al reproducir
ese paquete hay que exigir `--expected-budget exhausted`: el presupuesto esperado
no se toma del propio paquete. Por defecto es normal. No se descargan herramientas.
Exit 0 significa controles concluidos (incluye el control erróneo correctamente
identificado), 1 significa inconcluso y 2 indica ejecución/evidencia bloqueada.
Ningún exit code confirma una vulnerabilidad ni completa la plataforma.

`execution.json` conserva fuentes, consultas, respuestas, diagnósticos y referencias.
El replay regenera las fuentes desde código fijado; no ejecuta fuentes ni queries
suministradas por ese JSON. Las salidas son privadas y no se sobrescriben.

## Pruebas y límites

Los tests unitarios incluyen consultas reales a Z3, así como capturas y mocks
identificados para aislar la orquestación. `tests/fixtures/stateful_native_capture.json`
contiene una ejecución real de esta entrega, no un resultado inventado. Su hash
forma parte del snapshot de QA. Los mocks no cuentan como compilaciones adicionales.
La aceptación por comandos se ejecuta aparte sin esas sustituciones.

El CHC del compilador modela interacciones sucesivas, pero esta instancia tiene
un máximo explícito de tres operaciones admitidas. No se reivindica cobertura de
protocolos arbitrarios, inferencia automática de especificaciones, descubrimiento
original o ausencia universal de bugs. El compilador y el solver pueden tener
fallos: el replay usa los mismos motores y no verifica un certificado formal con
un comprobador externo. Las referencias son propias y conocidas, no un benchmark
ciego. No hay EVM, Slither, Foundry o conectores activos en esta entrega.

Referencia primaria del modelo CHC y sus límites:
https://docs.soliditylang.org/en/v0.8.30/smtchecker.html

La suite acumulativa se ejecuta ahora en ocho particiones exactas. Cada worker
conserva sus límites previos; el presupuesto total es mayor. Cada test debe
aparecer una sola vez bajo el mismo snapshot de código. No se omiten fallos.
