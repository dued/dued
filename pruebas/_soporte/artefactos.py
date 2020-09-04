from dued.artefactos import artefacto


@artefacto
def foo(c):
    print("Hm")


@artefacto
def noop(c):
    pass
