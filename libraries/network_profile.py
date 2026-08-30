"""Static-IPv4 NetworkManager keyfile generation for the --static-ip compile flag.

A deployed server needs a deterministic address for SSH. When --static-ip is passed,
the compiler bakes ONE NetworkManager keyfile connection into the airootfs at
CONNECTION_PATH (0600, root-owned); the verbatim rootfs clone / Calamares unpackfs
carries it onto the installed system, so the machine comes up on the fixed address.

Pure string/validation only -- no I/O -- so it unit-tests like the other libraries.
The keyfile format is NetworkManager's INI 'keyfile' plugin (the on-disk form of an
nmcli connection); DNS addresses are written as a ';'-terminated list per the format.
"""

from __future__ import annotations

CONNECTION_PATH = "/etc/NetworkManager/system-connections/azarch-static.nmconnection"


def is_valid_cidr(value: str) -> bool:
    """True for a well-formed IPv4 CIDR 'A.B.C.D/NN' (each octet 0..255, mask 0..32)."""
    if "/" not in value:
        return False
    addr, _, mask = value.partition("/")
    if not mask.isdigit() or not (0 <= int(mask) <= 32):
        return False
    octets = addr.split(".")
    if len(octets) != 4:
        return False
    for o in octets:
        if not o.isdigit() or not (0 <= int(o) <= 255):
            return False
        if len(o) > 1 and o[0] == "0":  # reject '01' style
            return False
    return True


def nmconnection_text(cidr: str, gateway: str | None = None,
                      dns: str | None = None) -> str:
    """The .nmconnection keyfile body for a static IPv4 wired connection.

    cidr: 'A.B.C.D/NN' -> address1. gateway (optional) -> appended to address1
    (the keyfile 'address1=IP/PREFIX;GATEWAY' form). dns (optional) -> a comma list
    that becomes a ';'-terminated dns= entry. Absent gateway/dns keys are omitted."""
    address1 = cidr if not gateway else f"{cidr};{gateway}"
    dns_line = ""
    if dns:
        joined = ";".join(a.strip() for a in dns.split(",") if a.strip())
        if joined:
            dns_line = f"dns={joined};\n"
    return (
        "[connection]\n"
        "id=azarch-static\n"
        "type=ethernet\n"
        "autoconnect=true\n"
        "autoconnect-priority=100\n"
        "\n"
        "[ipv4]\n"
        "method=manual\n"
        f"address1={address1}\n"
        f"{dns_line}"
        "\n"
        "[ipv6]\n"
        "method=auto\n"
    )
