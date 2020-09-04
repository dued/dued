from dued import artefacto


@artefacto(opcional=["bah"])
def foo(c, bah=False):
    print(bah)
