# Revisión de dependencias de NQC y SuperHunter

Desde la CLI de SuperHunter se puede consultar el catálogo de 200 proyectos, el grafo de dependencias de Census y los conflictos entre los seis perfiles Python de SuperHunter. El catálogo procede del [PR 110](https://github.com/josuechavando350-png/nexus-quant-capital/pull/110), commit `474846b11ea41f9d9f41c4aa6d7eda0cbf18d2f6`. La copia conserva exactamente los bytes públicos de ese JSON. La consulta conserva los identificadores históricos de los siete proyectos que aparecen también en el portafolio de 50.

Dos proyectos producen evidencia en esta revisión. Syft extrae paquetes y relaciones de los manifiestos copiados a un directorio temporal. cvc5 comprueba si los perfiles con versiones incompatibles pueden compartir un número dado de entornos. Las demás entradas siguen siendo consultables por su nombre en GitHub. Pertenecer al catálogo no acredita una ejecución.

## Reproducir

Usar Python 3.11 o posterior. Para producir evidencia se requieren Linux x86-64 y los dos ejecutables de las distribuciones indicadas. La CLI comprueba el SHA-256 de la copia privada que ejecuta. El verificador y el lector funcionan con la biblioteca estándar de Python. Los datos de entrada son los archivos del checkout local.

| Proyecto | Distribución probada | Commit de origen | SHA-256 del archivo de distribución |
|---|---|---|---|
| Syft 1.38.2 | [syft_1.38.2_linux_amd64.tar.gz](https://github.com/anchore/syft/releases/download/v1.38.2/syft_1.38.2_linux_amd64.tar.gz) | `bfe63f83dbaea88e22a5cfcd7d704c034c953730` | `6aa9a7b9e53c0f06e2d79fb24641cc1c856bb41702c282a577691f54bad94996` |
| cvc5 1.3.1 | [cvc5-Linux-x86_64-static.zip](https://github.com/cvc5/cvc5/releases/download/cvc5-1.3.1/cvc5-Linux-x86_64-static.zip) | `ea1b484fa54bfe56c0f8b3ac90a6e3e2f46441e7` | `1a1cda20d2df4938fa4944a69f33ddc9172e319ece0eed0aa09c4d7abede3ed1` |

Desde la raíz del checkout, sustituir las dos rutas por los binarios extraídos. El directorio de salida debe ser nuevo y externo al repositorio.

```bash
evidence_dir="$(mktemp -d)/evidence"
python3 -m superhunter review-product --syft /ruta/syft --cvc5 /ruta/cvc5 --out "$evidence_dir"
python3 -m superhunter verify-product --bundle "$evidence_dir"
python3 -m superhunter query-product --bundle "$evidence_dir" cvc5/cvc5 cryptography sha2
python3 -m superhunter.tests.benchmark_product_queries --bundle "$evidence_dir"
```

Para varias consultas, arrancar `query-product --bundle "$evidence_dir"` una vez y enviar un nombre exacto por línea por la entrada estándar. Devuelve un objeto JSON por línea o `null` si el nombre está ausente. Esa sesión consulta una instantánea verificada al arrancar. Para ver un cambio de los archivos fuente, generar y abrir un expediente nuevo.

## Qué demuestra

El inventario vincula cada observación con el archivo que fija su versión. El analizador de TOML y el lector de requisitos contrastan los resultados de Syft. Las relaciones Rust se contrastan con `Cargo.lock` y las dependencias directas de cada crate del workspace con su propio `Cargo.toml`. Una consulta de paquete devuelve las dependencias directas y los módulos de Census que dependen de él directa o transitivamente.

En Python se comprueban cotas crecientes de entornos hasta encontrar una solución. Si hay un conflicto, el motor elige primero el perfil cuya separación elimina más pares incompatibles y prueba si el resto admite un único entorno. Un segundo algoritmo construye particiones directamente a partir de las versiones declaradas, sin usar el grafo del solver. Devuelve un agrupamiento testigo y verifica tanto el mínimo como el resultado de la separación propuesta. Los dos métodos comparten las declaraciones originales. La verificación establece consistencia bajo el modelo de versiones declaradas. La compatibilidad binaria, la instalación conjunta y el comportamiento en ejecución requieren evidencia adicional.

Los expedientes locales incluyen los bytes originales de Syft, el resultado por consulta formal, los hashes de las consultas y entradas, y el informe reproducible. La verificación coteja el expediente con el checkout vigente. La autenticidad del host y la identidad del productor quedan fuera de esta comprobación.
