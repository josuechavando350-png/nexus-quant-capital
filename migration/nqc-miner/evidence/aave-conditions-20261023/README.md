# Condiciones iniciales Aave: prueba y observaciones

Esta entrega implementa un comando local de Miner para las condiciones
iniciales de la revisión 11 y un capturador limitado a tres bloques Ethereum.
No convierte esas condiciones en elegibilidad de ejecución ni en una señal
prospectiva. El significado y los límites están en
`docs/aave-initial-conditions.md`.

- `compiler/`: entrada y salida exactas del compilador, usando las fuentes
  originales y un adaptador sintético que llama a su función de validación.
- `rust-preflight.txt`: primer intento detenido por una anotación de tipo
  ausente en una prueba; se corrigió sin alterar el comportamiento del modelo.
- `rust-specific.txt`: comprobaciones iniciales y 539 casos diferenciales
  ejecutados mediante REVM. La auditoría general posterior incluye también
  los tres conjuntos de entradas históricas en el adaptador sintético.
- `python-specific.txt`: pruebas iniciales del capturador sin acceso a red.
- `public/`: siete getters × tres bloques × dos proveedores, más controles
  de cadena, finalización y encabezados: 96 registros en total.
- `trace-capability/`: dos solicitudes anteriores de prestateTracer terminaron
  en HTTPError. Se conservan petición y clase de error; no se obtuvo cuerpo
  de respuesta ni se infiere un código HTTP específico o una prohibición permanente.
- `local/`: reproducción sin red, vínculo con la publicación anterior,
  identidad del binario, entradas y salidas del comando de condiciones.
- `offline/`: auditoría de Rust, Python, Clippy, formato, identidad y aislamiento.
- `verification.json`: resultado final y hashes de entrega.
- `source-history.bundle`: conserva el commit del nuevo binario
  `5e88d25e72c4b03ad5e6acfca76e9a02fd501a21`. Requiere el commit `cc4abee` que
  ya conserva `evidence/aave-state-audit-20261023/source-history.bundle`;
  se verificó la integridad del bundle nuevo. No se afirma compilación hermética.

Reproducción del núcleo, con el compilador de hash fijado:

```sh
python research/build_aave_validation_harness.py --compiler /ruta/solc-0.8.27 --output /ruta/compilacion-nueva
cargo test --locked --offline --test aave_validation_tests -- --nocapture
python research/audit_aave_conditions.py --binary /ruta/nqc-miner --capture evidence/aave-conditions-20261023/public --output /ruta/auditoria-nueva
```

El generador vuelve a escribir el fixture sintético de forma determinista y
conserva las fuentes importadas sin cambios. Las fuentes corresponden a la
biblioteca cuyo runtime histórico se vinculó en la entrega anterior. La
captura pública no se repite al ejecutar la auditoría local.

El resultado debe leerse junto con los flags que siguen en `false`: estado
autenticado, estado previo a la transacción, elegibilidad ejecutable, validación
económica y activación. El liquidador procede retrospectivamente del evento;
la deuda se lee del token variable y su implementación externa sigue pendiente
de autenticación. Los datos corresponden a los mismos tres eventos. **43/100**.

La auditoría local reproduce los 96 registros. El estado de 26248113 pasa las
condiciones iniciales; 26248075 y 26248378 devuelven `HealthFactorNotBelowThreshold`.
Los tres coinciden con la ejecución de la función Solidity en el adaptador
sintético. Se conservan el primer error y las condiciones efectivamente
alcanzadas, sin afirmar que se hayan ejecutado comprobaciones posteriores a un
rechazo en la función original.
