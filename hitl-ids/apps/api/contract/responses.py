"""Bounded case response history; no service or HTTP-handler dependencies."""
from apps.api.contract.common import ApiModel,PageInfo
from packages.detection.response_approval import ResponseView


class ResponsePage(ApiModel):
    items: list[ResponseView]
    page: PageInfo
    case_revision: int
