#!/usr/bin/entorno python

import sys

stream = sys.stderr
stream.write(" ".join(sys.argv[1:]) + "\n")
stream.flush()

# vim:set ft=python :
