# Mutación guiada por cobertura EVM observada — perfil propio y acotado

Este módulo enlaza la cobertura por PC/arista JUMPI observada con la selección del
siguiente caso de prueba. **No analiza proyectos externos ni busca exploits de
producción**. A diferencia del perfil anterior de cobertura a posteriori,
selecciona un padre de mutación después de ejecutar cada caso.

## Diseño comprobable

1. `guide-owned-evm` fija la identidad del código Python actual y comprueba los
   hashes de `solc 0.8.30` y Geth `evm 1.17.10` ya custodiados. Compila dos
   controles aritméticos propios: `conservation` y `delayed_credit`.
2. Compila dos configuraciones por control (`legacy_unoptimized`,
   `ir_optimized`), verifica el constructor y arranca cada secuencia desde su
   estado inicial real (`debit=15`, `credit=0`, `steps=0`).
3. Ejecuta una secuencia inicial de cuatro llamadas con cantidad cero y gas
   normal; obtiene trazas nativas y vuelve a ejecutar cada llamada sin trazas.
   Contrasta estado persistente, retorno, reversiones, conciliación contable y
   dos oráculos aritméticos del laboratorio.
4. Después de cada ejecución cuenta posiciones PC y resultados de `JUMPI`,
   separados por contrato y configuración. Da prioridad como padre a casos que
   han añadido cobertura observable y, subsidiariamente, a rasgos poco comunes.
   Cada mutación es estrictamente acotada y determinista: cantidad sobre saldo,
   gas insuficiente y máximo `uint8`, con semilla declarada.
5. Registra todas las secuencias y trazas resumidas, incluso si una mutación
   añade **cero** nuevas posiciones o aristas. Ni la selección ni el resultado
   se convierten en supuesta vulnerabilidad.
6. `verify-guided-evm` no ejecuta instrucciones del paquete recibido: vuelve a
   compilar los controles **fijados en el código actual**, recrea exactamente
   las mutaciones por feedback y reejecuta Geth. Rechaza resultados o bitácoras
   modificados aunque se recalcule `COMPLETE.json`.

## Uso

Desde la carpeta que contiene `superhunter/`:

```bash
python3 - <<'PY'
import hashlib
from superhunter import quality
from superhunter.safe_io import canonical
print(hashlib.sha256(canonical(quality.source_snapshot())).hexdigest())
PY

python3 -m superhunter guide-owned-evm \
  --solc /ruta/solc-fijado --evm /ruta/evm-fijado \
  --expected-source HUELLACODIGO --seed 20261105 --candidates 2 \
  --out /privado/nuevo-expediente
python3 -m superhunter verify-guided-evm \
  --solc /ruta/solc-fijado --evm /ruta/evm-fijado \
  --expected-source HUELLACODIGO --bundle /privado/nuevo-expediente
```

El presupuesto es uno a tres candidatos, una base inicial y cuatro llamadas por
secuencia, dos contratos y dos perfiles. Son 32/48/64 llamadas trazadas según el
número de candidatos, más constructores. Los archivos de evidencia son privados,
las salidas nuevas nunca se sobrescriben y la consola omite datos sensibles.

## Límites

- Los rasgos son **PCs/aristas observados**, no cobertura de todos los caminos
  ejecutables ni cobertura universal de instrucciones; los PC deben coincidir
  con inicios de opcodes reales, no con datos inmediatos de `PUSH`.
- Una arista `JUMPI` indeterminada permanece indeterminada; no se declara tomada.
- Los límites de gas por llamada son de laboratorio y no se valoran en dólares.
- Los oráculos conocen estos controles propios; no prueban corrección de Z3,
  solc/Geth, ni equivalencia con otro motor independiente.
- Las reversiones no producen transferencias persistentes ni constituyen pérdidas.
- No se habilitan escaneos, RPC, firmas, transacciones, informes automatizados,
  creación de cuentas, acceso a objetivos externos ni operación 24/7.
- No se declara vulnerabilidad nueva, descubrimiento autónomo ni capacidad
  completa del sistema por haber aprobado estas pruebas de laboratorio.
