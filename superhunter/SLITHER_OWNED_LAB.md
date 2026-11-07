# SUPERHUNTER — segundo adaptador: ejecución fija de Slither (OWNED)

**Tecnología #6** del portafolio: https://github.com/crytic/slither. **Estado:** implementación de adaptador en rama aislada, PENDIENTE de ejecución nativa del analizador y QA completo sobre esta rama. No hay instalación de Slither en la infraestructura del usuario ni en GitHub, y ningún objetivo ajeno fue escaneado.

## Motivo y función

El módulo histórico `static_review.py` ya admite reportes Slither JSON y valida su relación con bytes de Solidity. Faltaba el paso previo: **ejecutar el analizador** sobre una fuente controlada, entregar un JSON real al importador y rechazar automáticamente fallos, manipulación de código o cambios del compilador. Este adaptador cierra la ruta de código para un único fixture OWNED de laboratorio y deja expresamente pendiente la certificación en máquina de análisis.

## Contrato de seguridad y límites

- La única fuente que puede analizarse es `Owned.sol` de 256 bytes, incrustada en `slither_owned_runner.py`. Contiene un uso deliberado de `tx.origin` como control negativo; no se despliega. Se fija el detector `tx-origin` y el número de versión del analizador a `0.11.6`.
- `native_compile.read_pinned_binary` exige el `solc 0.8.30` oficial para Linux amd64, con SHA-256 `f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7`. El adaptador copia esos bytes previamente comprobados a un directorio privado; no ejecuta directamente un archivo externo mutable.
- `slither_owned_worker.py` comprueba por segunda vez los hashes de la fuente y de solc; no admite URL/RPC, token, contrato externo, flags de búsqueda, shell ni entrada variable. El supervisor `owned_process.run` controla el proceso de grupo y limita a 90 segundos de pared. El worker fija CPU 35s, espacio virtual 2 GiB, archivo 2MB y 96 descriptores.
- **Esto no es un sandbox de red ni del host.** Un paquete Python comprometido podría realizar E/S ajena; por eso no está autorizado para procesar código de terceros y requiere sandbox/egress denegado antes de producción.
- `static_review.normalize` verifica posiciones del reporte contra bytes exactos y `static_review.import_report` almacena resultados originales privados con manifest y cadena de auditoría. Se mantiene `scanner_execution_verified=false` en la salida del importador porque la verificación offline **no reejecuta** Slither ni autentica al productor.
- Si Slither falla, expira, excede recursos, reporta error, cambia la fuente/solc o produce mappings incompletos, **no se concede PASS**. Cero alertas tampoco equivale a código seguro.

## Dependencias opt-in y comprobación

Usar un checkout aislado Linux amd64, no el entorno de producción:

```sh
python3 -m venv /privado/venv-slither
/privado/venv-slither/bin/python -m pip install -r superhunter/requirements-owned-slither.txt
/privado/venv-slither/bin/python -m superhunter doctor-owned-slither --solc /privado/solc-verificado
```

Las versiones directas se fijan (`slither-analyzer==0.11.6`, `crytic-compile==0.4.2`) pero **falta fijar hashes de transitivas y SBOM**. No utilizar esta instrucción para instalar en un host compartido sin previa revisión de licencia AGPL-3.0, versiones y aislamiento.

## Ejecución de contrato propio

```sh
/privado/venv-slither/bin/python -m superhunter run-owned-slither \
  --solc /privado/solc-verificado --repo-commit SHA40_DE_LA_REVISION \
  --out /privado/slither-owned-bundle-nuevo

/privado/venv-slither/bin/python -m superhunter verify-slither \
  --bundle /privado/slither-owned-bundle-nuevo
```

`repo-commit` es una declaración suministrada por el operador; el importador mantiene `repository_commit_verified=false`. La salida de ejecución indica `OWNED_SLITHER_IMPORTED_UNVERIFIED` y contiene contador de alertas ligadas a fuente, sin atribuir severidad final ni impacto. La segunda orden verifica **el paquete importado** sin reejecutar el scanner. Para obtener reproducción independiente del escaneo hará falta una segunda ejecución en entorno distinto.

## Pruebas y criterio de promoción

- Se agregaron pruebas `test_slither_owned_runner.py` para entrada fija, versión, output seguro, timeout, error de proceso, fuente sustituida, reporte incompleto, ausencia de source binding y resultado del importador contradictorio. Son pruebas de contratos con proceso **simulado**, no prueba real de Slither.
- No se ejecutó la suite completa de QA ni el ejecutable Slither en esta sesión. Los sistemas disponibles para el asistente no tienen Slither ni solc instalados, y el acceso a paquetes externos está restringido.
- Promocionar únicamente cuando: (1) ejecutar Slither real sobre OWNED fijo con salida comprobada y contra-controles; (2) repetirla en sandbox con egress denegado y versiones/hashes fijados; (3) ejecutar QA completo y verificador en el nuevo commit; (4) demostrar que la importación conserva los bytes y que los reportes alterados o erróneos son rechazados.

**Para futuras IAs:** el catálogo de 50 permanece separado de las 50 capacidades internas históricas, y el estado de #6 es **adaptador escrito; integración nativa NO certificada**. No ampliar el comando a otros repositorios o destinos sin una política de autorización real por programa y pruebas defensivas adicionales.
