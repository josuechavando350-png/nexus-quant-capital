# NQC666 — protocolo de medición, antes de medir el núcleo nuevo

Fecha: 2026-10-18. Base: 16e352225ba8a6a931834c4edf3d86d9a2924b7d.
Sólo laboratorio. Ningún resultado concede autorización comercial.

1. Validar SHA-256 del paquete NQC019; reconstruir C++ sin modificar fuentes en
   una copia externa. Repetir sus 20.055 comparaciones y 12 rechazos y cinco
   corridas de sus cuatro perfiles. Sus 119/250 ns son p99 históricos, no p50.
2. Contrastar Rust con el mismo oracle Python y el mismo corpus; comparar también
   todas las seis columnas con el ejecutable C++, incluyendo salidas parciales.
3. Medir llamadas individuales con CLOCK_MONOTONIC_RAW: mediana, p95, p99,
   p99.9, máximo y muestras sobre 3 us. No restar reloj ni eliminar picos.
4. Usar TSC serializado adicional para el filtro mínimo, calibrado cinco veces
   contra el reloj RAW. Publicar ticks originales y dispersión. No llamar ciclos
   de núcleo a los ticks TSC ni suponer frecuencia CPU estable en KVM.
5. Separar estrictamente llamadas individuales y lotes encadenados de 128
   decisiones: los percentiles de medias de lote NO son percentiles individuales.
   El siguiente índice depende del resultado anterior. Entrada variable,
   black_box, salida observable y desensamblado. Incluir calibración vacía.
6. Mínimo: coincidencia de generación y ventana temporal de 32 bytes, preparada
   tras pasar el control financiero. No incluye preparación, oráculo ni dinero.
7. Económico: port completo de NQC019 sobre datos decodificados. Defensivo:
   añade identidad, secuencia, pagos, oráculo y límites suministrados. Integrado:
   actualización decodificada, clasificación, control, actualización de prioridad,
   selección y opcional verificación final. NO mide socket/decodificación/EVM/builder.
8. Comparar referencia integrada con doble cálculo y versión que reutiliza el
   resultado recién obtenido sobre los mismos bytes inmutables. Ambas hacen la
   verificación completa final. Rechazar cambios de comportamiento.
9. Probar release sin LTO, thin LTO, fat LTO y target-cpu=native; tres repeticiones,
   orden reproducible aleatorio, misma CPU permitida. No correr benchmarks en paralelo.
   Registrar todos los resultados, incluso variantes más lentas.
10. Objetivos 50/20/10/5 ns: informar mediana y cola individual, por separado de
    medias encadenadas. Si el suelo del instrumento impide concluir, marcar
    NO DEMOSTRADO. Ningún máximo observado constituye garantía física universal.

Los corpus económicos son sintéticos NQC019 (gas 21k–221k/paso, importes ETH/WETH
expresados en enteros). Los eventos extendidos son fixtures sintéticos explícitos:
no describen oportunidades reales, recibos EVM ni condiciones de financiadores.
Un ensayo en KVM no establece un límite físico de hardware dedicado.
