# Repetición nativa de PR #84 — 7 de noviembre de 2026

## Identidad y alcance

Se cerró el pendiente nativo del [PR #84](https://github.com/josuechavando350-png/nexus-quant-capital/pull/84)
sobre el commit `09d8826643cee9c1c9cea06c125303625523540c` y el digest ejecutable
`b7eb0d8c628c2a0304a4d7e9fa602631d74eb4ba246d446f4b42d4ba0fd77ee9`.
Esta continuación modifica documentación solamente. Código, corpus, etiquetas,
referencias y pins de #84 permanecen intactos. Las ejecuciones se realizaron
el 8 de noviembre UTC, todavía 7 de noviembre en Ciudad de México.

## Resultados observados

| Perfil | Resultado | Alcance del denominador |
| --- | --- | --- |
| QA completo con SDK OpenTelemetry | 2,676 PASS; 0 fallos, errores o skips | Misma identidad y grupo de los 2,676 tests de #84; ocho workers |
| Telemetría | Dos spans, dependencias comprobadas, exportación de red desactivada | SDK local; sin Collector |
| Slither nativo | TP=1, TN=2, FP=0, FN=0 | Tres controles OWNED fijos; un detector |
| Cuotas, Geth y EELS | TP=4, TN=2, FP=0, FN=0 | Seis variantes propias conocidas |
| Autoridad temporal, Geth y EELS | TP=6, TN=4, FP=0, FN=1 | Once casos propios conocidos |

Los resultados nativos se verifican mediante reejecución en un proceso separado.
La verificación de QA y telemetría valida los expedientes sin volver a correr
la suite; su proceso no tiene SDK OpenTelemetry instalado. Los distintos
grupos no se suman en una puntuación global.

El falso negativo temporal sigue siendo `latent_revocation`. Comparte entradas
y observaciones con `clean_repeat` en el corpus histórico. El informe de
[cobertura de entradas](OWNED_AUTHORITY_COVERAGE.md) no lo convierte en una
detección. Los resultados de las variantes de evaluación también se preservan.

## Reconstrucción del entorno

Se utilizó Python 3.12.3 con soporte de sellado fcntl. El diagnóstico anterior
de Python 3.12.14, que carecía de esas constantes en este entorno, no se borra.

| Entorno separado | Identidad comprobada |
| --- | --- |
| OpenTelemetry | Ocho distribuciones; 403 archivos de runtime, más metadatos fijados |
| EELS | 23 distribuciones; 2,050 archivos de runtime |
| Slither | 51 distribuciones visibles; 2,313 archivos derivados de wheels; índice visible comprobado |

Los locks e inventarios son los del repositorio. La instalación inicial de
Slither mediante nombres de archivos wheel produjo 51 archivos `direct_url.json`
adicionales y fue rechazada con `SLITHER_DEPENDENCY_BYTES`, antes de ejecutar
el analizador. Se conservó ese diagnóstico. Un entorno nuevo, instalado por
nombre y versión desde un índice local de los mismos wheels, coincide con el
inventario sin eliminar metadatos ni cambiar pins. Cada distribución conserva
su directorio separado y el bootstrap fijado.

Los binarios se comprobaron antes de ejecutarlos:

| Binario | Versión | SHA-256 |
| --- | --- | --- |
| solc | 0.8.30+commit.73712a01 | `f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7` |
| Geth evm | 1.17.10-stable-1df30b18 | `d8cfddad15a8c601e7b069bc5973ad073dbc2d632b8c5ab50e513ef27c53d6da` |

La descarga primaria de solc devolvió HTTP 403; el mirror del repositorio
`ethereum/solc-bin` proporcionó bytes coincidentes con el pin. El archivo de
Geth provino de `gethstore.blob.core.windows.net`; URL completa, SHA del archivo
y diagnóstico de reconstrucción están en el expediente. No se efectuó una
nueva validación de firmas del distribuidor.

Se conservaron los límites de cada worker: QA usa ocho procesos secuenciales,
180 s de pared, 90 s de CPU, 2 GiB de espacio de direcciones y 20 MiB por archivo.
El mayor tiempo observado por worker QA fue 74.068 s. El staging del binario
Geth en el padre permite sus 42,001,080 bytes; no amplía los límites del worker.
Slither conserva su política específica de 90 s de pared, 35 s de CPU,
2 GiB y 2,000,000 bytes por archivo. No se certifica consumo agregado de host.

## Evidencia y repetición

Paquete: `SUPERHUNTER_ACEPTACION_NATIVA_PR84_20261107.zip`. Contiene los bundles
nativos, QA y telemetría, recibos de los ocho workers, logs, tiempos, diagnóstico
de reconstrucción, helpers y manifiesto SHA-256. El código acumulativo se
obtiene del commit indicado en GitHub; el ZIP no es un reemplazo del repositorio.
El manifiesto comprueba integridad, no autentica un productor independiente.

Los helpers conservados delegan en los verificadores reales. Con los entornos
fijados reconstruidos, los binarios en `native-tools/` y el checkout exacto en
`nexus-quant-capital/`, desde el directorio padre se ejecutó:

```sh
native-otel/bin/python3 -I -B superhunter/acceptance_helpers/run_owned_otel_prepare.py nexus-quant-capital pr84-prepared
native-slither-index/bin/python3 -I -B superhunter/acceptance_helpers/run_current_slither_acceptance.py nexus-quant-capital pr84 create
native-slither-index/bin/python3 -I -B superhunter/acceptance_helpers/run_current_slither_acceptance.py nexus-quant-capital pr84 verify
native-eels/bin/python3 -I -B superhunter/acceptance_helpers/run_joint_defensive_acceptance.py nexus-quant-capital pr84 finish
native-eels/bin/python3 -I -B superhunter/acceptance_helpers/run_joint_defensive_acceptance.py nexus-quant-capital pr84 verify
```

Las ejecuciones originales también asignaron un `-X pycache_prefix` distinto por
proceso. Antes de repetir, comprobar commit y digest contra las identidades
externas anteriores: los helpers calculan el digest del checkout recibido.
Los destinos de creación deben estar ausentes; preservar los expedientes
históricos y usar otra carpeta para una nueva corrida.

## Límites y continuación

Las pruebas usan fuentes propias fijas y casos conocidos, con cero objetivos
externos. Los workers nativos conservan el filtro de sockets; el host no está
aislado del sistema de archivos. Descargar dependencias fue un paso anterior
de preparación. No se comparan todos los aspectos de EVM ni se demuestra
independencia de productores: Geth y EELS comparten host, compilador y entradas.

El límite de repositorio se vuelve a verificar para esta entrega documental.
Los 642 archivos históricos permanecen intactos. Rust y las certificaciones
PFT/Census no se reejecutan ni recertifican por esta aceptación.

No hay vulnerabilidad original confirmada, operación 24/7 acreditada ni
integración en producción de los 50 candidatos. Avance global no determinado.
El siguiente paso acotado está en [CONTINUATION.md](CONTINUATION.md): definir
un corpus adicional de cobertura local con versión propia, preservando el
histórico y su omisión conocida.
