# Procedencia de los ensayos

Ejecutar desde migration/defense:

```bash
python3 -B tools/check_endurance_provenance.py --require-complete
```

El índice fija hashes de informes, commits y versiones. El comprobador contrasta cada fuente con los objetos Git locales sin reemplazos de objetos, exige la lista completa correspondiente al formato y rechaza esquemas desconocidos. Conserva expresamente el formato histórico sin schema de 0.20; este no registraba la huella del harness durante la ejecución. Ese límite aparece en el resultado.

Tres ensayos declarados completos: registro 0.19 (6320.964 segundos, 3361 inscripciones verificadas), receptor 0.20 (1800.00256 segundos, 270345 verificaciones) y receptor 0.22 (1200.00060 segundos, 144686 verificaciones). Las fuentes coinciden con sus commits respectivos; no son ensayos de la versión 0.24. Los datos son fixtures locales declarados.

Los cuatro criterios acotados son integridad de informes, pertenencia exacta de fuentes/versiones, completitud de duración/operaciones y rechazo de adulteraciones. Se conservan catorce pruebas de comportamiento y errores. La primera ejecución detectó una diferencia en el nombre del rechazo para la versión histórica; se corrigió sin admitir el dato inválido.

Esta comprobación hace reproducible el cotejo documental con Git. No acredita por sí sola que un informe sea verdadero, no certifica un reloj independiente y no aporta precisión productiva ni custodia externa.
