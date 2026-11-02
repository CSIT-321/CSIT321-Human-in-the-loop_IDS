from protocol_v3_1.environment import require_python
require_python()
"""Run adaptive only after a separate explicit opening receipt. Never opens an experiment."""
from protocol_v3_1.runner import cli
if __name__=='__main__': cli('adaptive')
