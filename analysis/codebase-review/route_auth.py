"""List every API route and whether an authentication dependency guards it (direct review aid)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hitl-ids"))
from fastapi.routing import APIRoute  # noqa: E402

from apps.api.main import create_app  # noqa: E402

AUTH = {"current_user", "current_readonly_user", "current_stream_user", "check"}


def names(dependant, out):
    for sub in dependant.dependencies:
        out.add(getattr(sub.call, "__name__", str(sub.call)))
        names(sub, out)
    return out


app = create_app()
routes = [r for r in app.routes if isinstance(r, APIRoute)]
unguarded = [f"{','.join(sorted(r.methods))} {r.path}" for r in routes if not AUTH & names(r.dependant, set())]
writes = [r for r in routes if r.methods & {"POST", "PUT", "PATCH", "DELETE"}]
print(f"{len(routes)} routes, {len(writes)} write routes, {len(unguarded)} without an auth dependency:")
print("\n".join(unguarded))
