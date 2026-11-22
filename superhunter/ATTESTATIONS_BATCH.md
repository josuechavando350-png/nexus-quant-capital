# Declaraciones Android en artefactos públicos fijados

El consumidor lee la declaración `application` del framework Android incluido con Apktool y dos paquetes de prueba revisados de Apktool y JADX. Solo el miembro `AndroidManifest.xml` se copia a un contenedor ZIP de datos. Los paquetes originales permanecen sin instalar. El recibo conserva la revisión y el digest de cada entrada.

| Función | Aporte observado |
|---|---|
| Apktool, ejecución | El AAPT2 distribuido por el proyecto decodifica el árbol XML binario del framework, de dos muestras y de una copia con un booleano alterado. Se verifica el SHA-256 del binario fijado en Git. La ejecución en Linux usa un namespace de red nuevo y dos montajes de solo lectura, el decodificador y el XML empaquetado. Se aplican límites de reloj, CPU, espacio de direcciones y descriptores. El binario proviene de la distribución upstream. Su compilación no se reprodujo en este lote. |
| JADX, referencia | El mapa de recursos y la definición de atributos resuelven `debuggable` a `0x0101000f` y `allowBackup` a `0x01010280`. Ambos deben ser booleanos admitidos en `AndroidManifestApplication`. El lector independiente compara el nombre, el identificador y el valor binario con la salida de AAPT2. |
| OWASP MASTG, referencia | Dos reglas XML indican qué declaraciones recoger. El resultado conserva por separado `true`, `false` y ausencia de declaración. No infiere valores efectivos dependientes de la plataforma. |

El framework y la muestra de recursos de JADX omiten ambos atributos. La muestra `empty_9patch` de Apktool declara ambos en `true`. En el control se invierte únicamente el booleano `debuggable`, con `allowBackup` en `true`. Ninguna observación representa por sí misma una vulnerabilidad.

Con `NQC_TRUST_TEST_SOURCES` apuntando al directorio `upstream` de los checkouts fijados, en Linux x86-64 con namespaces de usuario y red, `unshare`, `prlimit`, `bwrap`, Git, PyYAML y Python 3.12:

```sh
python3.12 -B -m unittest -v superhunter.tests.test_product_attestations_batch
```

[Expediente de las cuatro lecturas](product_supply/attestations-batch-receipt.json)

## Origen de las referencias

Los archivos publicados contienen el lector y las pruebas escritos para NQC, los identificadores de los controles y sus resultados. Cada XML, archivo APK y ejecutable nativo procede del submódulo local a la revisión de la tabla de pines. El commit conserva esta separación. El framework Android proviene de la distribución de Apktool y el mapa de recursos de JADX atribuye su fuente a Android Open Source Project. [Apktool y su licencia](https://github.com/iBotPeaches/Apktool/blob/fbaeb4779d7aaed2c3097cd496de2bc9150ab869/LICENSE.md) · [Proceso upstream para el AAPT2 modificado](https://github.com/iBotPeaches/Apktool/blob/fbaeb4779d7aaed2c3097cd496de2bc9150ab869/INTERNAL.md#building-aapt2-binaries) · [JADX LICENSE](https://github.com/skylot/jadx/blob/3cbbc2348141b7b51dbec2b227f334d6785547e6/LICENSE) · [JADX NOTICE](https://github.com/skylot/jadx/blob/3cbbc2348141b7b51dbec2b227f334d6785547e6/NOTICE)

OWASP Mobile Application Security Testing Guide publica las reglas originales bajo la licencia del proyecto, CC BY-SA 4.0. El lector consume las reglas originales sin modificarlas y conserva sus identificadores. Un paquete que incluya las reglas o distribuya una adaptación tendrá que conservar la atribución y atender a los términos de esa licencia. La distribución comercial de artefactos Android completos requiere revisar sus propios avisos y componentes. [Regla de depuración](https://github.com/OWASP/mastg/blob/e8183038d7a88c1ac962732d6e3f6e7f40a0251c/rules/mastg-android-debuggable-flag.yml) · [Reglas de backup](https://github.com/OWASP/mastg/blob/e8183038d7a88c1ac962732d6e3f6e7f40a0251c/rules/mastg-android-backup-manifest.yml) · [Licencia del proyecto](https://github.com/OWASP/mastg/blob/e8183038d7a88c1ac962732d6e3f6e7f40a0251c/License.md)
