# Conciliación QA de los sucesores #69–#78

Base recuperada: PR #78, commit `b18b23128a601498a3dba8fc0bfcbbd2eb726934`, árbol Git `08793a1481a217d5c61285171e92f6e5c1b93e65`. Se verificaron los blobs recuperados y el árbol completo antes de editar. Los cambios anteriores de #54/#55 y #68 están conservados; no se parte de una copia parcial anterior.

## Fallo reproducido y corrección

La base exacta ejecutó 2,550 pruebas: **8 fallos, 4 errores, cero skips**. El recibo fue verificado en otro proceso y permanece bloqueado. Una primera prevalidación no llegó a ejecutar QA porque faltaba la biblioteca Z3 del entorno; se restauró el acceso a los bytes originales con el SHA exigido, sin modificar capturas.

Tres causas distintas:

1. Cinco módulos nuevos de OpenTelemetry/Slither no figuraban en la asignación estable. Se fijan a sus workers observados en la base: `test_otel_qa` → 2; `test_slither_offline_endtoend` → 1; `test_slither_owned_runner`, `test_slither_control_pair`, `test_slither_pair_replay` → 7. Las identidades previas no cambian de worker. Se exige registro único y explícito de cada módulo descubierto.
2. `repository_boundary` rechazaba el anexo de AGENTS añadido por esos PR. Se conserva el pin Git original `6c2fe3771bad272bb1839aabc2b45ef636a16531` y se acepta únicamente su prefijo original de 1,107 bytes más el anexo revisado de 3,903 bytes, SHA-256 `74d63e642a1b6eecdb5cefbbd3fe6640cd8ba30d05cc620283b66a459dbd59cf`. Cualquier cambio del prefijo o del anexo, truncamiento o adición sigue rechazado. AGENTS no se edita.
3. La regresión nueva de Slither intentaba crear un archivo de 64 MB dentro del límite de escritura de 20 MiB. `qa_inputs.py` prepara antes de los workers **los mismos 64,000,001 bytes cero**; el test los enlaza como archivo regular y comprueba el rechazo por el límite real de 64,000,000 bytes antes de ejecutar el compilador. SHA-256 del input: `46e456b9b58dabe1e4f63d0a84a9306df12fb51be24051d91cc6d515d86e6df2`. No se reduce la muestra, simula su tamaño, cambia su identidad ni amplía un límite. Un invocador que ya aplica límites al proceso padre debe preparar este input antes de aplicarlos y mantener vivo su contexto durante QA. La ruta privada no se publica en el recibo.

## Validación de la corrección

- 102 pruebas focalizadas PASS, incluyendo el archivo real de 64,000,001 bytes con `RLIMIT_FSIZE = 20,971,520` bytes.
- **2,557/2,557 QA PASS**, cero fallos, errores o skips; siete regresiones nuevas, todas las 2,550 identidades previas retenidas. Verificación del paquete en otro proceso PASS.
- Digest fuente: `2087b61fb85a8ef65f21959a4e66a1f21ed33c2089b1610ddfb29c4e2cdaed7e`.
- Ocho workers; 180 s de pared, 90 s CPU, 2 GiB de memoria y 20 MiB por archivo sin cambios. Máximo observado por partición: 71.762948 s. No se afirma equivalencia de velocidad entre hosts.
- Python Linux 3.12.3, memfd y F_ADD_SEALS; PyYAML 6.0.3, cryptography 46.0.4 y Z3 4.13.3.0 SHA-256 `7accc397d4ac387468b09489bdaff9d82bfac4ca6a7e339b8fbb2167edf9c1c0`.
- Límite de repositorio PASS con 642 archivos históricos intactos. Verificador histórico sin cambios: PASS en copia histórica; **FAIL esperado sobre el árbol ampliado**, que no pertenece a su lista original. Nueve pruebas históricas de aislamiento PASS. Rust histórico no reejecutado porque sus archivos no cambian.
- Las ocho pruebas OpenTelemetry también pasan en un entorno separado con SDK/API 1.42.1 real y dependencias instaladas por hashes; todavía usan dobles de QA dentro de esas pruebas focalizadas. No son un perfil completo instrumentado ni un Collector desplegado.

Los tests Slither prueban el adaptador/importador sobre datos propios y reportes sintéticos; este cierre por sí solo no ejecuta el scanner nativo. Los recibos no autentican productores, ni prueban aislamiento completo del host. Cero vulnerabilidades originales confirmadas. Avance global no determinado. Ningún catálogo de 50 elementos se promueve a completo por este cierre.

## Conservación nativa sobre el mismo digest

Geth 1.17.10 y EELS recompilaron y ejecutaron los controles de cuotas y autoridad temporal, con verificación posterior en procesos separados. Cuotas: seis casos conocidos, TP 4 / TN 2 / FP 0 / FN 0. Autoridad temporal: once casos conocidos, TP 6 / TN 4 / FP 0 / FN 1; se conserva `latent_revocation`. No se suman estos grupos como una precisión global ni se cuentan repeticiones como muestras nuevas. Solc 0.8.30 y Geth conservan sus hashes originales; EELS conserva sus 23 dependencias exactas y su entorno separado.
