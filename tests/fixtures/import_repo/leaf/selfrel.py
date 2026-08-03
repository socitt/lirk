# Both spellings of an import within this target's own srcs. Neither is
# an edge to anywhere.
import selfmod
from . import selfmod as also_selfmod

PAIR = (selfmod.SELF, also_selfmod.SELF)
