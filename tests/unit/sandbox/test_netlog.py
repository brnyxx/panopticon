from __future__ import annotations

from panopticon.sandbox.netlog import (
    NetworkLogReason,
    NetworkLogSource,
    NetworkLogStatus,
    parse_blocked_egress_log,
    parse_dns_log,
    parse_proxy_log,
)


def test_dnsmasq_and_json_dns_logs_normalize_deterministically() -> None:
    text = "\n".join(
        (
            "dnsmasq[1]: query[A] Example.COM. from 10.0.0.3",
            '{"query":"xn--bcher-kva.example","qtype":"AAAA"}',
            "dnsmasq[1]: query[A] Example.COM. from 10.0.0.3",
        )
    )

    result = parse_dns_log(text)

    assert result.status is NetworkLogStatus.COMPLETE
    assert [(event.host, event.query_type) for event in result.events] == [
        ("example.com", "A"),
        ("xn--bcher-kva.example", "AAAA"),
    ]
    assert all(event.source is NetworkLogSource.DNS for event in result.events)


def test_tinyproxy_connect_formats_retain_host_and_port() -> None:
    result = parse_proxy_log(
        "\n".join(
            (
                "CONNECT example.com:443 HTTP/1.1",
                'INFO Established connection to host "Other.EXAMPLE" using file descriptor 7',
            )
        )
    )

    assert [(event.host, event.port) for event in result.events] == [
        ("example.com", 443),
        ("other.example", None),
    ]
    assert all(event.allowed is True for event in result.events)


def test_blocked_egress_text_and_json_are_explicit() -> None:
    result = parse_blocked_egress_log(
        "\n".join(
            (
                "DROP DST=203.0.113.5 DPT=8443 PROTO=TCP",
                '{"destination":"2001:db8::1","port":53,"protocol":"udp"}',
            )
        )
    )

    assert result.status is NetworkLogStatus.COMPLETE
    assert {event.host for event in result.events} == {"203.0.113.5", "2001:db8::1"}
    assert all(event.source is NetworkLogSource.BLOCKED_EGRESS for event in result.events)
    assert all(event.allowed is False for event in result.events)


def test_malformed_and_overflow_never_become_complete() -> None:
    malformed = parse_dns_log("not a dns log")
    overflow = parse_proxy_log("CONNECT example.com:443 HTTP/1.1", max_events=0)

    assert malformed.status is NetworkLogStatus.FAILED
    assert malformed.reason_code is NetworkLogReason.MALFORMED_LINE
    assert overflow.status is NetworkLogStatus.PARTIAL
    assert overflow.reason_code is NetworkLogReason.OVERFLOW
    assert overflow.diagnostics == ("OVERFLOW",)
