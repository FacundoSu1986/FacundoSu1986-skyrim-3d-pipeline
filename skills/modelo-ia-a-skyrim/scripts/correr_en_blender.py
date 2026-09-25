# -*- coding: utf-8 -*-
"""Que un script de Blender que revienta NO salga con 0.

Medido con Blender 4.4.1 en modo -b: una excepcion sin atrapar en el script de
--python imprime el traceback y Blender sale con **0**. `sys.exit(3)` si sale
con 3. Un control del pipeline que revienta a la mitad saldria "aprobado", y
quien lea solo el codigo de salida --un automatizador, CI-- no se entera.

Todo script de este directorio que corre en Blender termina con
`correr(main)`, y tests/test_montaje_puro.py lo exige: uno nuevo que llame a
main() suelto rompe la suite. `--python-exit-code 1` en la linea de comandos
tambien lo resuelve, pero depende de que quien lo invoca se acuerde.
"""
import sys
import traceback


def correr(main):
    """Corre main(). Cualquier excepcion imprime el traceback y sale con 1.
    SystemExit pasa tal cual: no hereda de Exception, asi que el `except` no
    la toca y `sys.exit(2)` sigue saliendo con 2."""
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
