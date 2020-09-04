from dued.artefactos import artefacto


@artefacto(default=True)
def foo(c):
    pass


@artefacto(default=True)
def biz(c):
    pass
