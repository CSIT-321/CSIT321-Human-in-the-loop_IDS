"""Run baseline only after a separate explicit opening receipt. Never opens an experiment."""
from protocol_v3.runner import cli
if __name__=='__main__': cli('baseline')
