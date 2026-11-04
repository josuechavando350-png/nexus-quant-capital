# Comprobación integrada y trazabilidad — entrega 4

## Cambio comprobado

El verificador anterior aceptaba una bitácora con un hash de entrada que no
correspondía a los datos numéricos, si los hashes del paquete se recalculaban.
Se reprodujo ese comportamiento en el código del commit `6657283`, sin objetivos
externos. `audit_links.py` ahora comprueba los 18 eventos esperados: autorización,
caso, hash de entrada, compromiso de salida, exclusión y cierre del mismo run.
También exige tipos exactos, UUID, funciones declaradas y orden temporal.

No equivale a una firma del productor: alguien que controla todo un paquete
puede fabricar una historia internamente consistente. No se atribuye autenticidad
remota a un hash, ni se afirma inmutabilidad física.

## Un comando para las comprobaciones existentes

```bash
python3 -m superhunter check --out /tmp/superhunter-qa-001
python3 -m superhunter verify-check --bundle /tmp/superhunter-qa-001
python3 -m superhunter capabilities
```

`check` ejecuta únicamente las pruebas propias del paquete, en un worker de
ruta fija. Registra cada ID y resultado, no interpreta un texto PASS aportado
por otro módulo. Comprueba las fuentes antes/después, tests obligatorios,
dependencias declaradas, archivos sin componente, errores y omisiones.
Cualquier skip, expected failure o resultado incompleto bloquea el gate.
Un archivo de ejecución nuevo sin asignación a un componente también lo bloquea.

Los siete grupos son IO, transporte, fuentes nativas, auditoría semántica,
laboratorio, QA y puntos de entrada. Sus relaciones son un manifiesto explícito:
**no es SlithIR, taint analysis ni cobertura de líneas calculada**. Que un grupo
tenga tests aprobados no demuestra todos sus comportamientos posibles.

Salida: recibo por test, hashes de fuentes, resultado por componente, log completo
y checklist de las 50 capacidades. `verify-check` contrasta de nuevo esos datos
contra el código y catálogo actuales sin ejecutar tests. No acepta evidencia de
una versión distinta. El recibo tampoco autentica un ejecutor remoto.

El worker usa el Python local con `-I -B`, ambiente reducido, límite de 90 s CPU,
2 GiB de espacio de direcciones, 20 MiB por archivo y timeout de 180 s. Es para
el código propio revisado, **no para ejecutar código hostil**. No añade RPC,
parámetros de objetivos, fuzzing ofensivo, contratos de ataque ni divulgación.
Los hooks de auditoría de Python no son un sandbox de seguridad.

## Estado de los 50 puntos

`capabilities.json` conserva los IDs 1..50. `CAPABILITIES.md` es su vista legible.
No hay implementaciones vacías para los pendientes: son requisitos, no módulos
que devuelvan éxito. Tres puntos tienen soporte parcial: 45 (worker local),
47 (Markdown de revisión/QA), 48 (regresión del propio paquete). Ninguno se marca
como capacidad completa. Las funciones de evasión, extracción de claves o
explotación autónoma se reformulan hacia validación defensiva, no se implementan
con su objetivo ofensivo original.

## Validación realizada

Se verificó que el paquete de partida completo coincide con el árbol Git
`3eab775dcf6bab9176b0f5d575da3f07300759a7`, correspondiente al commit `6657283`.
Baseline: 102 pruebas. Suite nueva: **157 pruebas, 0 fallos, 0 errores, 0 skips**.
Se ejecutaron el comando conjunto, su verificación posterior, el laboratorio
nativo y su verificación en procesos separados. Hay 20 pruebas de relaciones
semánticas y 35 de QA/catálogo, además de las 102 anteriores.

Los tests del verificador incluyen recibos sintéticos deliberadamente inválidos;
son entradas de pruebas, no evidencia de investigación. Los cinco escenarios
numéricos siguen siendo sintéticos. No se probó una vulnerabilidad de producción,
no se ejecutó Forge y no se completó el Hunter. La suite histórica NQC y el
verificador completo de aislamiento no se ejecutaron en esta entrega parcial;
se comprueba la conservación de árboles no modificados por identidad Git.

Documentación primaria consultada para la semántica de resultados y límites:
- Python 3.11, unittest: https://docs.python.org/3.11/library/unittest.html
- Python 3.13, audit hooks: https://docs.python.org/3.13/library/sys.html#sys.addaudithook
