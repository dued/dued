from dued import artefacto, Coleccion


@artefacto
def dummy(c):
    pass


hng = Coleccion(dummy, Coleccion("subcoleccion"))
