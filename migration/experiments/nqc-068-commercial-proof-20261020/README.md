# NQC068 - Prueba comercial integral

**Resultado: BLOCKED_EVIDENCE. Replay congelado por rechazo 403 del túnel durante la reconstrucción de tx0. Variante no ejecutada; neto desconocido; ganancia NQC demostrada: 0.**

Leer primero [RESULTADO_COMERCIAL.md](RESULTADO_COMERCIAL.md). Ver [MATRIZ_RPC.md](MATRIZ_RPC.md), [EVIDENCIA_CANONICA.json](EVIDENCIA_CANONICA.json), [CONTABILIDAD_INTEGRAL.json](CONTABILIDAD_INTEGRAL.json) y [PRUEBAS_Y_AISLAMIENTO.md](PRUEBAS_Y_AISLAMIENTO.md).

Se conservaron 46 respuestas RPC exitosas. Las dos cabeceras y las 41 transacciones/raíz del bloque fueron verificadas por hash. La falta de storage se reproduce usando solo los cuerpos guardados; el script de continuación online queda bloqueado después del rechazo. Nada de esto demuestra beneficio de la variante.

Reproducción permitida, sin red (requiere las versiones verificadas de forge/solc/cast ya disponibles):

```bash
python3 verify_chain_data.py /ruta/herramientas/cast
python3 reproduce_offline.py /ruta/herramientas
python3 -m unittest -v test_boundaries
sha256sum -c SHA256SUMS
```

El verificador de hashes se ejecuta antes de regenerar archivos: las reproducciones generan logs y timestamps nuevos. Las copias de productores originales son evidencia, no autorización de nuevas consultas. GIT_PUBLICATION.json identifica el commit de entrega. Ningún workflow nuevo, operación firmada, emisión ni gasto de fondos.
