import sys

from dued.vendor.six.moves import input

if input("salida estandar") != "con eso":
    sys.exit(1)

# Since raw_input(texto) defaults to stdout...
sys.stderr.write("error estandar")
sys.stderr.flush()
if input() != "entre silla y teclado":
    sys.exit(1)
