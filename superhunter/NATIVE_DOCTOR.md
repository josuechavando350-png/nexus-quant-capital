# Diagnóstico de requisitos del laboratorio

Antes de ejecutar una suite larga:

```sh
python -m superhunter doctor-owned-lab --solc /herramientas/solc --evm /herramientas/evm
```

Devuelve comprobaciones separadas de host, memoria sellada, paquetes QA,
biblioteca Z3 exacta de las capturas, compilador solc, Geth y dependencias del
segundo motor. Los perfiles `qa`, `owned_geth` y `owned_cross_evm` indican qué
prerrequisitos cumplen: que falte py-evm no invalida por sí mismo los otros dos.
Que falte el Z3 de las capturas bloquea QA, aunque los controles EVM fijos no lo usen.

El perfil fijado es Linux x86_64 y CPython 3.12. Android/Termux ARM no cumple ese
perfil por cambiar el nombre del ejecutable: se necesita un host compatible.
La comprobación de memoria intenta crear y sellar un descriptor con datos propios;
así detecta el Python que expone `memfd_create` pero carece de las constantes de sellado.

| Código | Acción local |
| --- | --- |
| `LINUX_X86_64_PYTHON312_REQUIRED` | Usar el host e intérprete del perfil fijado. |
| `SEALED_MEMORY_UNAVAILABLE` | Revisar soporte real de sellado del intérprete y kernel. |
| `QA_PACKAGE_MISSING_OR_DIFFERENT` | Instalar las versiones declaradas en los requisitos QA. |
| `Z3_LIBRARY_UNAVAILABLE` | Proporcionar la biblioteca del sistema requerida por las capturas. |
| `Z3_FIXTURE_BYTES_DIFFERENT` | Recuperar los bytes fijados en `QA_PARTITIONS.md`; la versión por sí sola no basta. |
| `PINNED_TOOL_MISSING_OR_DIFFERENT` | Usar las rutas de solc/Geth cuyos hashes exige el proyecto. |
| `SECOND_EVM_PACKAGES_MISSING_OR_DIFFERENT` | Instalar explícitamente el archivo de requisitos con hashes descrito en `OWNED_CROSS_EVM.md`. |

El diagnóstico no instala paquetes, descarga herramientas, ejecuta compiladores o
contratos, ni realiza consultas SMT. Z3 se comprueba por bytes sin cargar su
biblioteca nativa. Tampoco imprime rutas proporcionadas, variables del entorno o
mensajes internos de dependencias. La salida conserva el digest del código revisado.

Por defecto, `--profile all` exige todos los perfiles del motor seleccionado.
También se puede elegir `--profile qa`, `owned_geth` u `owned_cross_evm`; las otras
comprobaciones siguen visibles, pero no bloquean el perfil pedido.
`--second-engine execution-specs` comprueba los pins EELS en su entorno separado;
`py-evm` sigue siendo el valor predeterminado. Una instalación EELS puede estar
preparada para la comparación aunque sus paquetes no satisfagan el QA histórico.

Código de salida 0: los prerrequisitos del perfil solicitado están presentes. Código 2:
alguno está bloqueado o el diagnóstico no pudo completarse. Este resultado no
prueba que QA pase ni que el benchmark se haya ejecutado; los comandos de ejecución
y verificación siguen siendo obligatorios para esas afirmaciones.
