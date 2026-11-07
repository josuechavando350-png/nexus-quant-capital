# Tres controles propios con Slither real y originales conservados

El perfil actual `owned-slither-three-control-native-v2` ejecuta únicamente las tres fuentes propias ya publicadas en #78. Usa Slither 0.11.6, crytic-compile 0.4.2, solc 0.8.30 exacto y el detector fijo `tx-origin`. No admite fuentes, repositorios, URLs, RPC o flags suministrados por el operador.

## Procedencia explícita de v2

La primera aceptación v1 heredaba el nombre virtual `superhunter-owned/fixture` en el contexto del importador, que mantenía `repository_commit_verified=false`. v2 lo corrige al repositorio real `josuechavando350-png/nexus-quant-capital` y al commit `b18b23128a601498a3dba8fc0bfcbbd2eb726934`. `Owned.sol` es un archivo generado a partir de literales incrustados; no se afirma que ese nombre exista como archivo versionado en el commit.

Se verificaron por GitHub los dos contenedores originales: `slither_owned_runner.py`, blob `0a37fb11dd1bf43ff56dcbe84ceb0b1eb6da3051`, y `slither_control_pair.py`, blob `cb085a3958185194948df64e401bf47c3b287034`. Sus bytes locales coinciden. El perfil fija y revisa los hashes SHA-256/Git blob de ambos contenedores y los SHA-256 de los tres literales; cambiar cualquiera bloquea la procedencia histórica. La admisión y evaluación conservan ese inventario. No se alteran los contenedores ni las fuentes para dar PASS. La comprobación offline de bytes no autentica por sí sola pertenencia a un commit remoto ni al productor.

Los expedientes v1 conservados pertenecen a su revisión y no se reetiquetan como v2. Tres regresiones adicionales verifican identidad real, cambio de literal y cambio del contenedor. Su primer pase descubrió una colisión de nombre local al ensamblar el informe (10 errores); se corrigió el alias del módulo y las 37 pruebas Slither focalizadas pasaron. La validación v2 final se registra en [OWNED_DEFENSIVE_ACCEPTANCE.md](OWNED_DEFENSIVE_ACCEPTANCE.md).

## Problema corregido y cadena de evidencia

Dos intentos reales del adaptador anterior terminaron bloqueados: Slither devolvió correctamente `success=true,error=null,results={}` para el control limpio, pero el adaptador exigía `results.detectors`. Esos intentos no ejecutaron los otros dos controles y se conservaron como fallidos.

La nueva ruta conserva el JSON original, stdout, stderr, admisión y estado del proceso. Después crea una conversión explícita de ese único formato exitoso vacío a `results.detectors=[]`, con hashes de ambas representaciones. Los reportes con lista explícita se conservan byte por byte. Errores, campos ambiguos o secciones desconocidas no se convierten en un resultado limpio. **El importador genérico sigue rechazando la ausencia de detectors**; no se cambiaron sus reglas ni los fixtures originales.

El importador real conserva offsets y hashes de fuente, reporte, contexto y cadena de auditoría. El evaluador calcula FP y FN incluso cuando contradicen las expectativas. `EVALUATED` significa medición terminada, no todos los defectos detectados. El verificador recompila y reejecuta los tres casos en un proceso separado de aceptación; compara observaciones semánticas y revisa nuevamente los bytes del expediente original. Una repetición no añade tres muestras independientes.

| Control propio | Bytes | SHA-256 | Expectativa del detector |
|---|---:|---|---|
| positivo | 288 | `ef5475a13e367bef34010e339c082c85383ab85e4f229cd607899f5f52ce0c64` | alerta |
| limpio | 289 | `f4435d614ec0d890f56f06c6250bba4a60152255fa3f8d5ceec13952f9aba0f1` | sin alerta |
| comparación | 301 | `45e77d6d43ee7a13720323e48ed103e64447013c705af58f53e824ae3807df92` | sin alerta |

El control de comparación `tx.origin == msg.sender` ejercita una exclusión del detector: **no certifica seguridad del contrato**. Los tres casos son conocidos por quienes desarrollan el evaluador; no son holdout ni benchmark ciego.

## Dependencias y ejecución acotada

`owned_slither_pins.py` fija versiones, hashes de los 51 wheels e inventarios de 2,313 archivos derivados de ellos, incluidos código, METADATA, WHEEL, entry points y licencias. La instalación convencional sobrescribía cinco archivos de documentación compartidos entre paquetes; se rechazó. El entorno aceptado instala cada wheel intacto en su directorio propio bajo `site-packages/owned_distributions/<nombre-normalizado>`. Un único archivo `.pth` contiene 51 rutas relativas y ninguna instrucción ejecutable.

El checker recorre dos veces ese inventario cerrado antes de ejecutar el scanner y vuelve a comprobarlo después. Rechaza archivos añadidos, symlinks, ubicaciones mezcladas, cambios de metadatos y exceso de tamaño. RECORD/INSTALLER/REQUESTED generados por pip, launchers no utilizados y cachés pyc están fuera de esa identidad. Los procesos de aceptación usan `-I -B -X pycache_prefix=<directorio_privado_nuevo>`. Los pins verifican bytes instalados, no autenticidad del productor, integridad de memoria, confianza del intérprete/stdlib o la ejecución previa de archivos de inicio Python. No usar la API embebida para certificar un proceso anfitrión ya cargado.

**Límite adicional identificado:** el inventario anterior cierra los directorios del entorno, pero aún no rechaza metadatos de otra distribución visible por una ruta Python externa. Una prueba con solo METADATA propio temporal elevó el índice visible de 51 a 52 y el checker anterior siguió admitiendo sus 51 pins; no se creó ni ejecutó código de ese control. El entorno real de esta aceptación tiene exactamente 51 distribuciones visibles, comprobadas por separado. Cerrar también ese índice es el siguiente endurecimiento; esta aceptación no certifica entornos alterados.

Para reconstrucción manual se deben recuperar únicamente los wheels cuyos hashes constan en PINS, comprobar sus licencias y contenido y usar `--no-index --no-deps --no-compile --require-hashes --target` para cada distribución en un entorno vacío CPython 3.12 Linux amd64. No utilizar la lista histórica de dos dependencias directas como lock del perfil nuevo. `dependencies.bootstrap_bytes()` define exactamente el `.pth`; `verify_dependencies()` exige el inventario completo. Los helpers y manifiestos de la aceptación conservada documentan los comandos efectivos y los hashes revisados. No se instala ni descarga nada al invocar el evaluador.

El worker verifica fuente y compilador antes de lanzar Slither. Fija 90 s de pared, 35 s CPU, 2 GiB de espacio virtual, 2 MB por archivo y 96 descriptores. Crea un filtro de sockets Linux x86_64 antes de importar Slither; rechaza sockets heredados y comprueba denegación AF_INET, AF_INET6 y AF_UNIX. El filtro se hereda al compilador. La biblioteca libseccomp exacta (`b4d9140a7797ccf3ac14f5d9d579b64f157111662940cb8330c632b11a8cea8e`) se carga desde bytes memfd sellados después de verificar su hash. Esto no es aislamiento completo del sistema de archivos o del host, ni prueba de independencia entre productores.

## Comandos y límites de aceptación

El párrafo de resultados v1 al final de esta sección es histórico de #81; no se atribuye su digest a v2.

Desde el checkout exacto, con el entorno cerrado anterior y un prefijo de caché nuevo:

```sh
python -I -B -X pycache_prefix=/privado/cache-nuevo -c 'import sys; sys.path.insert(0,"/checkout-exacto"); from superhunter.owned_slither_native import main; raise SystemExit(main())' evaluate-owned-slither-native --solc /privado/solc-exacto --expected-source DIGEST_QA --out /privado/expediente-nuevo
python -I -B -X pycache_prefix=/privado/cache-verificador-nuevo -c 'import sys; sys.path.insert(0,"/checkout-exacto"); from superhunter.owned_slither_native import main; raise SystemExit(main())' verify-owned-slither-native --solc /privado/solc-exacto --expected-source DIGEST_QA --bundle /privado/expediente-nuevo
```

`DIGEST_QA` se obtiene del inventario ejecutable de la revisión exacta, no de un commit anterior. Los directorios de salida deben ser nuevos y privados. No publicar originales de terceros; esta aceptación contiene exclusivamente controles propios.

Validación final: **2,608/2,608 QA PASS**, cero fallos/errores/skips, con SDK real de OpenTelemetry y verificador separado sin SDK. Se retienen las 2,574 identidades previas en sus workers y se añaden 34 regresiones focalizadas aprobadas. Ocho workers y presupuestos 180 s pared / 90 s CPU / 2 GiB / 20 MiB intactos; máximo observado 71.971036 s. Digest ejecutable `9ceab53076a3437996abe869928cf19bdbf8fea852158cf6b126f9c30c8f5851`. El primer pase de 30 tuvo un error en un informe sintético de falso positivo por omitir type/name; se corrigió únicamente ese doble de test, preservando el fallo y las fuentes originales. Una prueba mantiene explícitamente FP 1/FN 1. Las pruebas unitarias usan scanner simulado y no se presentan como ejecución nativa. La ejecución nativa separada obtuvo TP 1/TN 2/FP 0/FN 0 y su replay coincidió; sus bytes corresponden al mismo digest aprobado por QA. Tres controles negativos sobre copias del expediente real (fuente, conversión y conteos alterados y vueltos a sellar) fueron rechazados. Límite del repositorio PASS; 642 archivos históricos preservados. Geth/EELS y Rust no se reejecutaron para este digest; su evidencia anterior no se le atribuye.

El candidato externo #6 no se promueve a integración completa por estos tres casos. No hay prueba de generalización, certificación de contratos, objetivos externos, hallazgo original ni recompensa prometida. Avance global no determinado.
