"""Adapters normalize evidence without assigning operational priority."""
from typing import Protocol, TypeVar
from packages.contracts.canonical import CanonicalAlert

InputT = TypeVar("InputT", contravariant=True)


class DetectorAdapter(Protocol[InputT]):
    def adapt(self, output: InputT) -> CanonicalAlert: ...
