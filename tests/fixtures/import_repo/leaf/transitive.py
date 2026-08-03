# Reaches //base:base through //mid:mid rather than directly: allowed,
# because the closure is what the fingerprint covers. `json` is stdlib
# and must not be looked at at all.
import json

from base.base import VALUE
from mid.mid import DOUBLED

TOTAL = VALUE + DOUBLED + len(json.dumps({}))
