from __future__ import annotations

from panopticon.sandbox.trace import TraceAbsenceStatus, TraceStatus, parse_strace


def test_forked_child_read_and_connect() -> None:
    result = parse_strace(
        "\n".join(
            (
                '10 1700000000.100 chdir("/home/pano/work") = 0',
                '10 1700000000.200 openat(AT_FDCWD, "data.bin", O_RDONLY) = 4',
                "10 1700000000.300 fork() = 11",
                '11 1700000000.400 read(4, "x", 1) = 1',
                (
                    "11 1700000000.500 connect(5, {sa_family=AF_INET, "
                    'sin_port=htons(443), sin_addr=inet_addr("192.0.2.1")}, 16) = 0'
                ),
            )
        )
    )

    assert result.status is TraceStatus.COMPLETE
    child_read = result.events[3]
    assert child_read.pid == 11
    assert child_read.operation == "read"
    assert child_read.path == "/home/pano/work/data.bin"
    assert child_read.confirmed
    assert result.events[4].operation == "connect"


def test_truncation_marks_partial_and_absence_unknown() -> None:
    result = parse_strace('7 1700000004.000 openat(AT_FDCWD, "/home/pano/decoy" <unfinished ...>')

    assert result.status is TraceStatus.PARTIAL
    assert result.events == ()
    assert result.absence_status is TraceAbsenceStatus.UNKNOWN
