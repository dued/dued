import os

from pytest import skip

from dued import Contexto, Config


class Contexto_:
    class sudo:
        def caso_base(self):
            # NOTE: Se asume que un usuario cuya contraseña es 'mipass' ha 
            # sido creado y agregado a la configuración de sudo con 
            # contraseña (no sin contraseña); y que este usuario es el que 
            # ejecuta la suite prueba. Solo para correr en Travis, básicamente.
            if not os.environ.get("TRAVIS", False):
                skip()
            config = Config({"sudo": {"password": "mipass"}})
            resultado = Contexto(config=config).sudo("chubaca", ocultar=True)
            assert resultado.stdout.strip() == "root"
