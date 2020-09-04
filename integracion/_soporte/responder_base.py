import sys

from dued.vendor.six.moves import input

if input("¿Cuál es la contraseña?") != "Subamarillo":
    sys.exit(1)
