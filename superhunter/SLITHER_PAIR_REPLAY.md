# SuperHunter — comparación verificable de dos pares Slither (offline)

**Alcance:** herramienta #6 del portafolio externo. **Estado: código escrito, revisión y pruebas completas PENDIENTES**. Este cambio no instala Slither, no ejecuta contratos ni analiza objetivos ajenos. Es sucesor del [control positivo/limpio](SLITHER_PAIR_GATE.md).

## Por qué

Un par exitoso (contrato fijo con `tx.origin` y control limpio con `msg.sender`) no demuestra que una segunda ejecución reproduzca el resultado. Tampoco un manifiesto SHA-256 autoconsistente autentica al productor. El nuevo módulo `slither_pair_replay.py` obliga a entregar **dos paquetes privados diferentes** y dos huellas SHA-256 **recibidas por separado**, de sus respectivos `COMPLETE.json`.

Los dos paquetes se vuelven a verificar mediante `slither_control_pair.verify_pair` y `static_review.verify_report`. Además de las entradas fijadas, la comparación incluye las ubicaciones en código, fingerprints, clasificación declarada, conteos, estado, versiones, scope y commit. Discrepancias o faltantes provocan rechazo. Una coincidencia se reporta exclusivamente como `TWO_SLITHER_PAIRS_AGREE_UNAUTHENTICATED`.

### Obtención de las dos ejecuciones

En un entorno propio Linux con compilador y Slither admitidos (y, para seguridad, un sandbox con egress cerrado), se generan **por separado** los pares con `run-owned-slither-pair`. Si se pretende demostrar independencia, ejecutar el segundo en otro host y conservar identidad del productor mediante evidencia adicional; **este módulo no certifica ese requisito**. La función de comparación no requiere Slither instalado, solamente las dependencias ya usadas para verificar expedientes.

Los valores esperados SHA-256 deben registrarse **antes de comparar**, fuera de los propios paquetes. Por ejemplo:

```sh
sha256sum /privado/primer-par/COMPLETE.json
sha256sum /privado/segundo-par/COMPLETE.json

python3 -m superhunter compare-owned-slither-pairs \
  --first /privado/primer-par --second /privado/segundo-par \
  --expected-first-sha256 SHA256_PREVIAMENTE_GUARDADO_1 \
  --expected-second-sha256 SHA256_PREVIAMENTE_GUARDADO_2 \
  --out /privado/comparacion-nueva

python3 -m superhunter verify-owned-slither-comparison \
  --first /privado/primer-par --second /privado/segundo-par \
  --expected-first-sha256 SHA256_PREVIAMENTE_GUARDADO_1 \
  --expected-second-sha256 SHA256_PREVIAMENTE_GUARDADO_2 \
  --bundle /privado/comparacion-nueva
```

La salida privada contiene `comparison.json`, `REVIEW.md` y `COMPLETE.json`. Un cambio en cualquiera de los originales o derivados, incluso después de recalcular sus hashes internos, no puede convertirse en PASS mientras se conserven las anclas externas legítimas.

## Garantías y exclusiones

- Se cotejan **dos pares de archivos diferentes**, no se afirma que procedan de hosts, operadores o ejecuciones independientes; las dos evidencias podrían estar falsificadas por el mismo productor.
- `scanner_executed_here=false`, `separate_host_proven=false`, `producer_authenticated=false`, `independent_execution_proven=false`, `vulnerability_confirmed=false`.
- Solo se comparan **resultados normalizados**. Ni esto ni un `PASS` de QA demuestran la ausencia de vulnerabilidades, la eficacia general del detector, ni un reporte bounty.
- Los snapshots contienen metadatos derivados y hashes; los originales sensibles permanecen fuera del repositorio.
- El catálogo #6 sigue sin promocionarse a integración validada de producción: Slither y solc genuinos, QA completo sobre el código nuevo y sandbox deben verificarse todavía.

## Validación de esta entrega

Se añadieron pruebas de unidad en `tests/test_slither_pair_replay.py`: dos anclas correctas, hash falso, misma ruta o subárbol, symlink, divergencia de fingerprints/impactos/fuentes/commits, pérdida de campos, resumen contradictorio, adulteración resellada, expedientes incompletos, salida insegura y CLI que no revela rutas. **Son pruebas con simulación de los dos verificadores subyacentes** y, por ahora, no consta ejecución de la suite de la rama en el checkout completo ni ensayos con Slither real.

**Siguiente trabajo:** correr esas pruebas con los módulos auténticos del repositorio; ejecutar los dos pares Slither/solc en máquinas aisladas con versiones/hashes fijados; repetir el cotejo y publicar recibos verificables sin originales privados. No inferir superioridad ni ingresos a partir de estos controles.
