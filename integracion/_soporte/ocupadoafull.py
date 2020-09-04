"""
Un programa que sólo hace el trabajo, produce stdout/stderr e ignora stdin.

Útil para medir el uso de la CPU del código que hace interfaz con ella sin
esperar que el entorno de prueba tenga mucho de nada.

Acepta un único argumento de Argv, que es el número de ciclos a correr.
"""

import sys
import time


num_cycles = int(sys.argv[1])

for i in range(num_cycles):
    salida = "[{}] Este es mi stdout, hay muchos como este, pero...\n".format(i)
    sys.stdout.write(salida)
    sys.stdout.flush()
    err = "[{}] Errar es humano, equivocarse es sobrehumano.\n".format(i)
    sys.stderr.write(err)
    sys.stderr.flush()
    time.sleep(0.1)
