"""Drop-in shim: importing ``pythreejs`` yields ``anythreejs``.

Used to run *unmodified* pythreejs-based code (e.g. upstream plopp) against
anythreejs. Put this file's directory on PYTHONPATH:

    PYTHONPATH=tests/shims pytest <pythreejs-based test suite>
"""

import sys

import anythreejs

sys.modules[__name__] = anythreejs
