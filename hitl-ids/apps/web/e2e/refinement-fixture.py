"""Run routing UI checks with entirely synthetic, disposable data; never touch demo.db."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import serve_routing_rehearsal as routing
from serve_s16_rehearsal import build_pristine_fixture

# Reuse the existing routing fixture setup, replacing only its initial database copy.
# The existing runner owns the TemporaryDirectory and removes it on shutdown.
with patch.object(routing.shutil, "copy2", side_effect=lambda _source, target: build_pristine_fixture(target)):
    routing.main()
