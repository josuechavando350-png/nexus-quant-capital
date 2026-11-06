# SUPERHUNTER — fuzzing de secuencias EVM, corpus propio delimitado

## Alcance ejecutable

Nueva ruta `evm_sequence_fuzz.py` conectada a la CLI, la compilación fijada,
`evm_execution`, conciliación de unidades NQC, `AuditLog` original DIABLO y QA.
No usa objetivos externos, contratos o transacciones de producción, RPC,
contratos provistos por usuarios, firmas ni capital. No detecta automáticamente
vulnerabilidades nuevas: explora **dos controles aritméticos propios**, uno de
conservación y otro con una aserción que revierte al tercer paso.

El corpus usa nueve casos frontera iniciales y mutaciones reproducibles controladas
por semilla; acepta presupuestos entre 9 y 24 secuencias, cuatro operaciones por
secuencia. Los presupuestos son límites de ejecución, no porcentaje de cobertura.

Para cada control, `solc 0.8.30` oficial genera bytecode de creación y ejecución
con dos perfiles: legacy sin optimizador y vía IR optimizado. Se valida la misma
fuente, ABI, layout, función y metadata. Geth EVM ejecuta realmente el constructor
sobre almacenamiento vacío y cada secuencia posterior sobre su propio estado.
Las secuencias independientes pueden procesarse mediante tres workers, pero
sus operaciones **siempre conservan el orden**.

Por operación se comparan estado persistente, retorno, reversión, gas perfil,
prestate y hash de salida observada con dos oráculos aritméticos de Python.
Una segunda comparación examina los resultados entre las dos configuraciones
del compilador. El conciliador existente comprueba unidades internas por cuenta
y no registra transferencias procedentes de operaciones revertidas. Si cualquiera
discrepa, no se genera un paquete favorable.

## Comandos

Calcular primero el hash del código y los tests actuales desde el checkout:

```bash
python3 - <<'PY'
import hashlib
from superhunter import quality
from superhunter.safe_io import canonical
print(hashlib.sha256(canonical(quality.source_snapshot())).hexdigest())
PY
```

```bash
python3 -m superhunter fuzz-owned-evm \
  --out /privado/caso-nuevo --solc /privado/solc-verificado \
  --evm /privado/evm-verificado --expected-source HASH_EXTERNO \
  --seed 20261105 --cases 9
python3 -m superhunter replay-owned-evm \
  --bundle /privado/caso-nuevo --solc /privado/solc-verificado \
  --evm /privado/evm-verificado --expected-source HASH_EXTERNO
```

La creación requiere una carpeta nueva fuera del checkout. El verificador vuelve
a compilar y ejecutar los casos; **no ejecuta bytecode, argumentos ni instrucciones
de los archivos de evidencia recibidos**. Los binarios están fijados por tamaño,
versión y SHA-256. El hash externo es un ancla local de versión, no firma ni
autenticación de un productor remoto. Los paquetes completos son privados.

## Limitaciones obligatorias

- Los mismos `solc` y EVM se utilizan en ambos perfiles; no hay motor independiente.
- Los dos oráculos comparten las reglas conocidas del control. No prueban
  exhaustividad de estados, equivalencia universal ni descubrimiento original.
- Las aserciones fallidas revierten y NO demuestran una pérdida persistente.
- `simulation_only=false` significa ejecución de bytecode en una EVM real **local**;
  no significa ejecución en una blockchain ni autorización para interactuar con ella.
- No se mide costo monetario de gas, liquidez, fondos explotables, precisión de
  hallazgos, recall de benchmarks reales ni probabilidad de bounty.
- La verificación repetida vuelve a utilizar los mismos ejecutables y modelos.
- **No se autoriza** activación de workflows, RPC, reportes automáticos o trading.

Esta unidad amplía el repertorio de pruebas EVM, no completa los catálogos
27/50/25 ni cambia sus estados por pasar pruebas propias.
