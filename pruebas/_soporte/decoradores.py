from dued.artefactos import artefacto


@artefacto(alias=("bar", "otrobar"))
def foo(c):
    """
    Foo el bar.
    """
    pass


@artefacto
def foo2(c):
    """
    Foo el bar:

      codigo ejemplo

    Agregado en 1.0
    """
    pass


@artefacto
def foo3(c):
    """Foo el otro bar:

      codigo ejemplo

    Agregado en 1.1
    """
    pass


@artefacto(default=True)
def biz(c):
    pass


@artefacto(help={"porque": "Motivo", "quien": "Quien al lado oscuro"})
def holocron(c, quien, porque): # Artefacto Sith : https://www.starwars.com/databank/sith-holocron
    pass


@artefacto(posicional=["pos"])
def un_posicional(c, pos, nonpos):
    pass


@artefacto(posicional=["pos1", "pos2"])
def dos_posicionales(c, pos1, pos2, nonpos):
    pass


@artefacto
def posicionales_implícitos(c, pos1, pos2, nonpos=None):
    pass


@artefacto(opcional=["miopc"])
def valores_opcionales(c, miopc):
    pass


@artefacto(iterable=["milista"])
def valores_iterables(c, milista=None):
    pass


@artefacto(incremento=["verbose"])
def valores_incrementables(c, verbose=None):
    pass
