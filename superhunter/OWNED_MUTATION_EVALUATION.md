# SUPERHUNTER — medición de mutaciones conocidas con pruebas EVM nativas

Esta unidad reúne dos familias **propias, deliberadamente diseñadas** como controles
positivos y negativos: distribución durante una pausa y operaciones por un
remitente no autorizado. **NO es un benchmark ciego** ni un descubrimiento de
vulnerabilidades originales; los nombres y etiquetas de los mutantes son conocidos.

## Contrato de medición

- `score-owned-evm` ejecuta los dos productores ya existentes, usando exclusivamente
  las fuentes y secuencias fijas del paquete y los ejecutables `solc` y Geth verificados.
- El analizador de observaciones deriva su decisión de los estados realmente
  persistidos, la identidad del llamante, la pausa y el estado de reversión;
  **no usa el nombre de la variante ni su etiqueta de verdad para decidir**.
- Cada caso es una combinación de **familia y variante del contrato**. Hay cuatro
  casos en total: dos controles protegidos y dos mutantes conocidos. La segunda
  configuración de compilación sirve de contraste; no duplica muestras estadísticas.
- Cuando falta una llamada, hay inconsistencia de estado, un resultado EVM no
  esperado o una diferencia entre las dos compilaciones, la evaluación se **bloquea**.
  Nunca sustituye una medición incompleta por una decisión negativa.
- `benchmark._section` reutiliza el contador de TP/FP/TN/FN con un cálculo por
  conjuntos independiente. No se inventan costos monetarios ni tiempos por caso.
- La etiqueta `low` es una categoría **sintética obligatoria para el formato del
  corpus**, NO representa severidad de un fallo real. Las cifras del ensayo no
  extrapolan a contratos desconocidos.
- `verify-owned-evm-score` exige la huella de código externa, **recompila y ejecuta
  de nuevo** ambas familias, recalcula las predicciones y exige identidad exacta
  de la evidencia, métricas, reporte y cadena AuditLog de DIABLO. Un manifiesto
  recalculado tras alterar la decisión no puede reemplazar el replay.

## Ejecución

```bash
python3 -m superhunter score-owned-evm \
  --solc /ruta/segura/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/segura/evm --source-digest SHA256_DEL_SNAPSHOT_QA \
  --out /ruta/privada/nueva
python3 -m superhunter verify-owned-evm-score \
  --solc /ruta/segura/solc-linux-amd64-v0.8.30+commit.73712a01 \
  --evm /ruta/segura/evm --source-digest SHA256_DEL_SNAPSHOT_QA \
  --bundle /ruta/privada/nueva
```

Toda la evidencia queda en un directorio privado, nunca se sobrescribe. La
CLI no ofrece objetivos, repositorios, hosts, RPC, claves, binarios arbitrarios
(no fijados) ni parámetros de contratos externos. No distribuye ni ejecuta
exploits. En el perfil evaluado, un hallazgo positivo significa **transición
persistente incompatible con una propiedad DECLARADA** en el escenario local;
no significa elegibilidad para recompensas.

## Límites de investigación

Una muestra de cuatro variantes conocidas y dos familias no mide precisión
sobre protocolos reales. La enumeración de escenarios no prueba ausencia de
fallos en los controles protegidos fuera del corpus. Ambos perfiles ejecutan el
**mismo compilador y la misma EVM**; no son verificadores independientes en sentido
criptográfico o de diversidad de implementación. Las etiquetas están escritas en
el código; cualquier evaluación ciega futura debe separar el corpus y sus
etiquetas del desarrollo. Los resultados de esta unidad se distinguen de cualquier
cobertura estadística real, y de los programas externos, que permanecen pendientes.
