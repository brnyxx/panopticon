from __future__ import annotations

from pathlib import Path

from panopticon.sandbox.base import ContainerSpec
from panopticon.sandbox.network import (
    CapabilityStatus,
    NetworkPlan,
    NetworkSession,
    plan_network,
)


def test_rootless_plan_keeps_limited_attribution_visible() -> None:
    plan = plan_network(rootless=True)

    assert plan.proxy is CapabilityStatus.PARTIAL
    assert plan.dns is CapabilityStatus.PARTIAL
    assert plan.direct_drop is CapabilityStatus.PARTIAL
    assert plan.reason == "ROOTLESS_ATTRIBUTION_PARTIAL"


def test_network_session_applies_proxy_and_dns_without_mutating_spec(tmp_path: Path) -> None:
    spec = ContainerSpec(
        image="registry.example/pano@sha256:" + "a" * 64,
        command=["serve"],
        env={},
        decoy_home=tmp_path,
    )
    session = NetworkSession(
        network="pano-run-internal",
        egress_network="pano-run-egress",
        proxy_id="proxy",
        dns_id="dns",
        proxy_ip="10.0.0.2",
        dns_ip="10.0.0.3",
        plan=NetworkPlan(
            network="pano-run-internal",
            proxy=CapabilityStatus.COMPLETE,
            dns=CapabilityStatus.COMPLETE,
            direct_drop=CapabilityStatus.COMPLETE,
        ),
    )

    configured = session.apply(spec)

    assert spec.network == "pano-net"
    assert configured.network == "pano-run-internal"
    assert configured.dns == "10.0.0.3"
    assert configured.proxy_url == "http://10.0.0.2:8888"
