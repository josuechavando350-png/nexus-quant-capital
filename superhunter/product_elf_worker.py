"""Read ELF loader metadata from the private copies prepared by the inventory command."""
import json
from pathlib import Path
import sys


def main():
    sys.path.insert(0, str(Path('wheel').resolve()))
    import lief
    config = lief.ELF.ParserConfig()
    config.parse_relocations = False
    config.parse_notes = False
    config.parse_overlay = False
    config.parse_symbol_versions = False
    config.parse_symtab_symbols = False
    config.parse_dyn_symbols = False
    files = {}
    for path in sorted(Path('bin').iterdir()):
        binary = lief.ELF.parse(str(path), config)
        files[path.name] = {'class': binary.header.identity_class.name, 'machine': binary.header.machine_type.name,
                            'byte_order': binary.header.identity_data.name, 'interpreter': binary.interpreter,
                            'needed': list(binary.libraries)}
    print(json.dumps({'version': lief.__version__, 'files': files}))


if __name__ == '__main__':
    main()
