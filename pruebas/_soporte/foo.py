from dued.artefactos import artefacto


@artefacto
def miartefacto(c):
    pass


@artefacto
def arg_basico(c, arg="val"):
    pass


@artefacto
def args_multiples(c, arg1="val1", otroarg="val2"):
    pass


@artefacto
def bool_basico(c, mibool=True):
    pass
