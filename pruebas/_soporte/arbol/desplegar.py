"Cómo implementar nuestro código y configs."

from dued import artefacto


@artefacto(default=True)
def omnipresente(c):
    "Implementar en todos los objetivos."
    pass


@artefacto(alias=["db_servers"])
def db(c):
    "Implementar en nuestros DB servers."
    pass


@artefacto
def web(c):
    "Actualiza y rebota los servidores web."
    pass
