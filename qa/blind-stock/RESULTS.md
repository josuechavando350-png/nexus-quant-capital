# Resultado del ensayo ciego

Hunter se probó sobre doce implementaciones nuevas de un registro de almacén de NQC. Ocho contenían un defecto sembrado y cuatro eran variantes sanas. Cada implementación procesó los mismos 16 lotes. El evaluador encontró al menos una salida incorrecta en cada variante etiquetada como defectuosa.

| Información disponible | Verificación | Casos defectuosos detectados | Casos omitidos | Casos sanos con alerta | Salidas incorrectas detectadas |
| --- | --- | ---: | ---: | ---: | ---: |
| Registro interno | Saldos | 3/8 | 5 | 0/4 | 25/59 |
| Registro interno | Saldos, contador y subtotal | 5/8 | 3 | 0/4 | 34/59 |
| Comprobantes independientes | Saldos | 4/8 | 4 | 0/4 | 30/59 |
| Comprobantes independientes | Saldos, contador y subtotal | 6/8 | 2 | 0/4 | 39/59 |

El último renglón es la medición principal especificada antes de crear los casos. De las 192 salidas, 133 eran correctas. Las cuatro modalidades produjeron cero alertas en esas 133 salidas.

En el primer caso omitido por la modalidad principal, los dos renglones del registro aparecían en orden inverso. En el segundo, la segunda partida indicaba una unidad de menos aunque los saldos reflejaban la cantidad correcta. El primer caso pasó inadvertido en todas las modalidades. El segundo produjo una alerta cuando Hunter recibió los movimientos declarados por el registro. Usar comprobantes independientes permite descubrir diferencias contables que un registro internamente coherente oculta. Contrastar saldos finales todavía puede dejar pasar errores en las partidas individuales.

El cegamiento se aplicó al proceso clasificador. La misma autoría preparó las variantes y el ensayo. El resultado mide detección contable con observaciones de ejecución y cuatro controles sanos. La transferencia a otros programas y la detección por lectura de código requieren otra evidencia.

## Rastro de la prueba

1. [Protocolo y adaptador congelados antes de crear los casos](https://github.com/josuechavando350-png/nexus-quant-capital/commit/b50a2805e4e9dddabcc8c11098b8e03378d3e39c)
2. [Compromiso de los casos, etiquetas y evaluador antes de predecir](https://github.com/josuechavando350-png/nexus-quant-capital/commit/0b97182fbec1ba185a468b91ad4899ee288dfde4)
3. [Predicciones registradas antes de puntuar](https://github.com/josuechavando350-png/nexus-quant-capital/commit/ad9bf33d3fdb1adc29bc899aa8fdc426b2ea53b3)

El artefacto de CI incluye las observaciones, los veredictos anónimos y el resultado del evaluador. La ejecución comprueba que reproducen las huellas registradas. Repetir el experimento con la clave pública sirve para verificar la primera ronda.
