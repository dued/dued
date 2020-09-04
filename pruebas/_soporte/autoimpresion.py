from dued.artefactos import artefacto
from dued.coleccion import Coleccion


@artefacto
def nop(c):
    return "You can't see this"


@artefacto(autoimpresion=True)
def yup(c):
    return "¡es la fuerza!"


@artefacto(pre=[yup])
def pre_chequeo(c):
    pass


@artefacto(post=[yup])
def post_chequeo(c):
    pass


sub = Coleccion("sub", yup)
hng = Coleccion(nop, yup, pre_chequeo, post_chequeo, sub)
