# Aceptación conjunta de QA, cuotas y autoridad temporal

El perfil `whole-qa-quota-and-temporal-authority-v1` exige que QA completo y los dos grupos nativos correspondan al **mismo digest de código**. El perfil anterior de [cuotas](OWNED_PLATFORM.md) no incluía la [autoridad temporal](OWNED_AUTHORITY_EVM.md); el nuevo consumidor verifica ambas y conserva sus evidencias por separado.

## Qué termina y qué no certifica

`OWNED_DEFENSIVE_ACCEPTANCE_COMPLETE` significa que se ejecutaron las etapas prescritas y sus verificadores. No significa que todos los defectos fueron detectados. El caso conocido `latent_revocation` sigue como FN: su secuencia no ejerce revocación. Las fuentes, etiquetas y secuencias históricas no se modifican para eliminar esa omisión.

| Grupo | Unidad de evaluación | Casos conocidos | Defectuosos | Controles correctos |
|---|---|---:|---:|---:|
| Cuotas | una variante propia de fuente | 6 | 4 | 2 |
| Autoridad temporal | un modelo propio con su secuencia fija | 11 | 7 | 4 |

Los denominadores no se suman en una precisión global. Tampoco se convierten llamadas, compilaciones o replays en muestras independientes. Se conservan errores, abstenciones, falsos positivos, omisiones y las ablaciones originales. En particular, la ablación que confunde éxito de la EVM con autorización de aplicación debe seguir mostrando sus falsos positivos.

## Secuencia de aceptación

1. `prepare-owned-platform` ejecuta todos los tests en el entorno QA exacto y conserva recibos, catálogo, controles locales y la identidad de código. Ocho workers secuenciales; 180 s pared, 90 s CPU, 2 GiB y 20 MiB por archivo, sin ampliar límites.
2. `finish-owned-defensive` comprueba esa preparación, copia exclusivamente su inventario permitido, ejecuta cuotas y su replay Geth/EELS, después autoridad y su replay Geth/EELS. Los artefactos se revisan otra vez antes del marcador conjunto. Si una etapa falla, no hay marcador final de aceptación conjunta; los marcadores de hijos no lo sustituyen.
3. `verify-owned-defensive` se ejecuta en otro proceso. Verifica los recibos de QA y recompila/repite los dos grupos nativos. Vuelve a calcular métricas, comprueba los informes contra los bytes y revisa nuevamente inventarios y marcadores después de los replays. El verificador **no vuelve a ejecutar QA** ni autentica al productor de los recibos.

Comandos desde un checkout exacto, con salidas privadas nuevas fuera del checkout:

```sh
# Entorno QA: PyYAML 6.0.3, cryptography 46.0.4 y Z3 exacto.
python -B -m superhunter prepare-owned-platform --out /privado/preparacion

# Entorno EELS separado, 23 dependencias fijadas y herramientas exactas.
python -B -m superhunter finish-owned-defensive --prepared /privado/preparacion --out /privado/conjunto --solc /herramientas/solc --evm /herramientas/evm --expected-source DIGEST
python -B -m superhunter verify-owned-defensive --bundle /privado/conjunto --solc /herramientas/solc --evm /herramientas/evm --expected-source DIGEST
```

El padre prepara la imagen exacta de Geth de 42,001,080 bytes antes de los límites originales del worker; no se reduce el binario ni se amplía el límite de los workers. QA mantiene cryptography 46.0.4 y EELS su 45.0.7. El perfil no acepta un intérprete, contrato, datos, dirección, RPC o objetivo arbitrario.

Slither mantiene su propio entorno de 51 paquetes y su expediente de tres controles. Puede evaluarse con el mismo digest, pero no se afirma que este perfil conjunto ejecute Slither: son evidencias separadas con unidades y dependencias distintas.

## Regresión de la CLI directa

La entrada `python -m superhunter.quality` ejecutaba `main` antes de registrar muchos componentes añadidos históricamente. Por ello rechazaba un expediente que la CLI del paquete y el verificador importado aceptaban. Se reprodujo en #80 sobre sus bytes publicados; se conserva el diagnóstico. El guard de `main` ahora queda después del registro completo.

Dos pruebas de procesos separados, con recibos **explícitamente fabricados para tests**, reprodujeron el fallo antes de la corrección. Después verifican coincidencia para un recibo coherente y bloqueo al quitar una prueba obligatoria tardía. Estos recibos no son evidencia de ejecución real. Las 33 pruebas del consumidor conjunto también usan dobles nativos explícitos; la aceptación Geth/EELS real se registra aparte.

## Estado de esta iteración

**2,646/2,646 QA PASS**, cero fallos/errores/skips, con SDK OpenTelemetry real y verificador separado sin SDK. Se retienen las 2,608 identidades anteriores en sus workers y se agregan 38 regresiones: 33 del consumidor conjunto, dos de CLI y tres de procedencia. Las 37 pruebas Slither focalizadas (34 anteriores y tres nuevas) pasan. Ocho workers y límites intactos; máximo observado 74.484587 s. Digest final `d7694017e1cc912935db4e46f7f9247ebefccf473cc4f07e314dc5a7895144a9`.

Un primer pase de 2,643 tests también pasó, pero precede la corrección de procedencia; se conserva como revisión intermedia, no como aceptación del digest final. El perfil Slither v2 real obtuvo TP 1/TN 2/FP 0/FN 0 y su replay separado coincidió sobre el digest final. La aceptación Geth/EELS real terminó en 118.966 s y su verificador separado en 58.040 s. Cuotas: TP 4/TN 2/FP 0/FN 0; autoridad: TP 6/TN 4/FP 0/FN 1, con latent_revocation visible. Una copia que eliminaba la omisión y recalculaba sus hashes fue rechazada después de repetir ambos grupos (57.950 s); el original permanece intacto.

La CLI directa corregida volvió a ejecutar las mismas 2,646 pruebas completas en 342.247 s, sin stubs del checker; ambas entradas de verificación aceptaron ese expediente. Esa repetición no aumenta el denominador ni sustituye el primer perfil instrumentado. Límite del repositorio PASS y 642 archivos históricos intactos. Rust histórico no reejecutado.

Pendiente separado: cerrar el índice global de distribuciones Slither visibles por otras rutas Python. El entorno usado aquí tiene 51 exactas; un control de solo metadatos propios mostró que el checker anterior no rechazaba una adicional fuera del entorno. Ver el límite documentado en SLITHER_NATIVE_EVIDENCE.md.

Los dos motores comparten host, compilador, inputs y especificación. No se demuestra autenticidad de productores, identidad criptográfica del caller, aislamiento completo del host, presupuesto agregado, benchmark ciego, generalización o recertificación histórica. Sin objetivos externos, despliegues, fondos, firmas ni transacciones operativas. Avance global no determinado; ninguna vulnerabilidad original confirmada.
