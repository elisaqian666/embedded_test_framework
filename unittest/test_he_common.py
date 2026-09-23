from embedded_framework.helpers.he_common import CommonHelpers
from embedded_framework.helpers.he_network import NetworkHelper


def test_common_helpers_include_network_helper() -> None:
    assert isinstance(CommonHelpers().network, NetworkHelper)
