from __future__ import annotations

from panopticon.sandbox.trace import TraceReason, TraceStatus, parse_strace


def test_parse_filesystem_process_and_network_syscalls() -> None:
    result = parse_strace(
        "\n".join(
            (
                '101 1700000000.100 openat(AT_FDCWD, "/home/pano/read.txt", O_RDONLY) = 3',
                '101 1700000000.200 openat(AT_FDCWD, "/home/pano/write.txt", O_WRONLY|O_CREAT) = 4',
                '101 1700000000.300 newfstatat(AT_FDCWD, "/home/pano/meta", {}, 0) = 0',
                '101 1700000000.400 readlink("/home/pano/link", "target", 4096) = 6',
                '101 1700000000.500 execve("/usr/bin/node", ["node"], 0x0) = 0',
                (
                    "101 1700000000.600 connect(5, {sa_family=AF_INET, "
                    'sin_port=htons(443), sin_addr=inet_addr("192.0.2.1")}, 16) = 0'
                ),
                (
                    '101 1700000000.700 sendto(5, "x", 1, 0, {sa_family=AF_INET6, '
                    'sin6_addr=inet_pton(AF_INET6, "2001:db8::1")}, 28) = 1'
                ),
                (
                    "101 1700000000.800 bind(6, {sa_family=AF_UNIX, "
                    'sun_path="/tmp/pano.sock"}, 110) = 0'
                ),
                "101 1700000000.900 clone(child_stack=NULL, flags=CLONE_VM) = 202",
            )
        )
    )

    assert result.status is TraceStatus.COMPLETE
    assert [event.operation for event in result.events] == [
        "read",
        "write",
        "stat",
        "read",
        "exec",
        "connect",
        "send",
        "bind",
        "clone",
    ]
    assert result.events[0].path == "/home/pano/read.txt"
    assert result.events[1].path == "/home/pano/write.txt"
    assert result.events[2].path == "/home/pano/meta"
    assert "sin_addr" in (result.events[5].peer or "")
    assert result.events[-1].result == 202


def test_unfinished_and_resumed_lines_reassemble_at_start_timestamp() -> None:
    result = parse_strace(
        "\n".join(
            (
                '55 1700000001.100 openat(AT_FDCWD, "/home/pano/chunk" <unfinished ...>',
                "55 1700000001.900 <... openat resumed>, O_RDONLY) = 7",
            )
        )
    )

    assert result.status is TraceStatus.COMPLETE
    assert len(result.events) == 1
    assert result.events[0].timestamp == 1700000001.1
    assert result.events[0].path == "/home/pano/chunk"


def test_escaped_path_is_decoded_without_losing_unicode() -> None:
    result = parse_strace(r'9 1700000002.000 open("/home/pano/a\n\u2603", O_RDONLY) = 3')

    assert result.events[0].path == "/home/pano/a\n☃"


def test_malformed_unsupported_and_truncated_coverage_stays_visible() -> None:
    mixed = parse_strace(
        "\n".join(
            (
                "not a trace line",
                "7 1700000003.000 ioctl(3, 0, 0) = 0",
                '7 1700000003.100 open("/ok", O_RDONLY) = 3',
            )
        )
    )
    truncated = parse_strace("7 1700000004.000 connect(3, {sa_family=AF_INET <unfinished ...>")
    failed = parse_strace("garbage")

    assert mixed.status is TraceStatus.PARTIAL
    assert TraceReason.MALFORMED_LINE.value in mixed.diagnostics
    assert "UNSUPPORTED_SYSCALL:ioctl" in mixed.diagnostics
    assert truncated.status is TraceStatus.PARTIAL
    assert truncated.reason is TraceReason.TRUNCATED
    assert failed.status is TraceStatus.FAILED
    assert failed.events == ()
