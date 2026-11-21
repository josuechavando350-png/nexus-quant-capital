# Evidencia pasiva de infraestructura

Este lote usa dos consumidores de NQC. La revisión de la ABI verifica las reglas declaradas por el proceso de cómputo sobre Linux x86-64. La revisión de capturas entrega eventos de dos archivos públicos de regresión al analizador forense existente. Los recibos registran los objetos Git, hashes SHA-256, operaciones, resultados y controles rechazados.

| Proyecto | Función probada | Tipo |
|---|---|---|
| strace/strace (#50) | Su tabla x86-64 aporta el número y la aridad de las 25 llamadas usadas en las 32 reglas del perfil de NQC. | Datos de referencia |
| aquasecurity/tracee (#87) | Los identificadores de eventos y los nombres/posiciones de argumentos se contrastan con la tabla de strace y las comparaciones de NQC. | Datos de referencia |
| cilium/tetragon (#88) | Las declaraciones del kernel resuelven por nombre las posiciones sometidas a 17 comparaciones y permiten verificar la intención documentada del perfil. | Datos de referencia |
| inspektor-gadget/inspektor-gadget (#90) | Las tablas bidireccionales convierten las 25 identidades a número y decodifican cada número de vuelta para contrastarlo con las otras fuentes. | Datos de referencia |
| wireshark/wireshark (#91) | Cuatro representaciones de una captura DHCP aportan un control de equivalencia de contenido y tiempo. Se verifican número de registro, época, delta y huella por trama. | Corpus y oráculo |
| secdev/scapy (#92) | RawPcapReader y RawPcapNgReader decodifican las cuatro representaciones de DHCP y una captura NTP. Las 18 observaciones corresponden a seis eventos únicos en la línea temporal de NQC. | Ejecución |
| the-tcpdump-group/tcpdump (#95) | La captura y la salida esperada de la prueba de NTPv4 permiten comprobar de manera independiente época, roles cliente/servidor y longitud. | Corpus y oráculo |

La revisión ABI rechaza una posición de argumento cambiada y una correspondencia número/nombre cruzada. Comprueba el contrato declarado, sin instalar filtros ni observar llamadas en otro proceso. La revisión pasiva limita Scapy a un lector aislado sin red, sin subprocess adicionales y con límites de tiempo y memoria. Un lector independiente de PCAP clásico contrasta las tramas y los tiempos. Una captura abreviada se rechaza por longitud. Una inversión del orden de NTP produce una contradicción en el consumidor forense. Las marcas de tiempo proceden de los archivos de regresión. La verificación de estos casos públicos no acredita atribución, causalidad, intrusión ni descubrimiento original.

## Reproducción

Con CPython 3.12 sobre Linux, Git, unshare con espacios de usuario/red disponibles y los siete checkouts inicializados en `upstream/`, ejecutar desde la raíz del producto. Las dos revisiones y las pruebas funcionan sin acceso externo.

```sh
python3.12 -B -m unittest superhunter.tests.test_product_infra_batch superhunter.tests.test_infra_batch_pcap
python3.12 -B - <<'PY'
from pathlib import Path
from superhunter.product_infra_batch import review
from superhunter.product_review import sha
from superhunter.safe_io import canonical, strict_json

supply = Path('superhunter/product_supply')
expected = {}
for name in ('infra_batch_abi.json', 'infra_batch_captures.json'):
    expected.update(strict_json((supply / name).read_bytes()))
actual = review(Path('upstream'))
assert actual == expected
print(len(actual), sha(canonical(actual)))
PY
```

Resultado del lote: 7 participantes y SHA-256 `8f647e3e038eda2df9319d33b24ab3dc7afccffcca2b37976bcd7572335c0f4a`. Las referencias anteriores se consumen como datos. Para Scapy se cargan los 12 módulos Python fijados en su árbol Git desde un directorio temporal sin dependencias de terceros instaladas.
