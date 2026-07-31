"""
specification_fulltext -- render the COMPLETE component listing as a formatted plain-text
file (documentations/SPECIFICATIONS_COMPONENTS_FULL.txt).

Where the SVG is the readable at-a-glance shape of the distribution (a curated
subset per layer) and SPECIFICATIONS_GENERAL.md is the prose/subsystem view, this
file is the exhaustive one: EVERY package in the transitive closure, nothing
collapsed, each with its real metadata and a human-language description of what it
is and does.

The human description is NOT hand-written and NOT from an LLM: it is the official
Arch package description (the `%DESC%` field of the package's record in the
core/extra/multilib databases -- the exact one-liner shown on archlinux.org and by
`pacman -Si`), plus the upstream project URL. That means it is real, offline,
deterministic, and can never drift from the package set.

The layout is designed to be pleasant to read directly AND trivially machine-
parseable: each component is a block introduced by a `### name` header and a set
of `key: value` lines with stable keys, so the file can be grep'd or parsed back
into structured records without a second data source. The interactive twin of
this listing is the browsable HTML map (specification_html).
"""

import textwrap

import specification_classify as K
import specification_svg

# Stable one-line explanation of each edition tag, shown in the legend and used
# as the long form when a component is displayed on its own.
EDITION_LABEL = {
    "az'arch": "az'arch  (Az'arch Component: in the set only because Az'arch "
               "added it on top of stock archiso)",
    "stock": "stock    (Stock Arch: already on the stock archiso releng medium)",
}
EDITION_SHORT = {
    "az'arch": "az'arch",
    "stock": "stock",
}

# Human-language, one-line role for each dependency layer, so the reader
# understands what "layer 3" means without cross-referencing the SVG. Derived
# from the single source of truth (specification_svg.LAYER_DEFS) so the two never drift.
LAYER_ROLE = [f"{title} -- {subtitle}" for title, subtitle in specification_svg.LAYER_DEFS]

RULE = "=" * 78
THIN = "-" * 78


def _layer_of(pkg, category, height):
    # Mirror the SVG's layer assignment so the two artifacts agree.
    return specification_svg.layer_of(pkg, category, height)


def _fmt_size(nbytes):
    if nbytes >= 1024 ** 3:
        return f"{nbytes / 1024 ** 3:.2f} GiB"
    if nbytes >= 1024 ** 2:
        return f"{nbytes / 1024 ** 2:.1f} MiB"
    if nbytes >= 1024:
        return f"{nbytes / 1024:.1f} KiB"
    return f"{nbytes} B"


def _wrap_field(label, text, width=78, indent=None):
    """Wrap a 'label: text' field, hanging the continuation under the value."""
    if indent is None:
        indent = " " * (len(label) + 2)
    body = textwrap.fill(
        text, width=width,
        initial_indent=f"{label}: ",
        subsequent_indent=indent,
    )
    return body.split("\n")


def _name_list(names, label, width=78):
    """Render a possibly-long list of package names as a wrapped field.

    Returns a list of lines. Empty list -> a single '(none)' line so the reader
    always sees the field and knows it was genuinely empty, not omitted.
    """
    if not names:
        return [f"{label}: (none)"]
    joined = ", ".join(names)
    indent = " " * (len(label) + 2)
    # break_on_hyphens=False so a hyphenated package name (e.g. xdg-user-dirs,
    # vlc-plugin-ffmpeg) is never split across two lines: it stays one
    # whitespace-free token, which keeps the file honest and the parser trivial.
    wrapped = textwrap.fill(joined, width=width,
                            initial_indent=f"{label}: ",
                            subsequent_indent=indent,
                            break_on_hyphens=False)
    return wrapped.split("\n")


def _component_block(pkg, packages, resolved, tiers, tags):
    """Return the list of text lines for one component's full entry."""
    rec = packages.get(pkg, {})
    tag = tags[pkg]
    edges = resolved["edges"]
    heights = tiers["heights"]

    deps = sorted(edges.get(pkg, ()))
    dependents = sorted(tiers["rev"].get(pkg, ()))
    height = heights.get(pkg, 0)
    layer = _layer_of(pkg, tag["category"], height)
    desc = rec.get("desc") or "(no description in the Arch package database)"
    url = rec.get("url") or ""
    version = rec.get("version", "?")
    repo = rec.get("repo", "?")
    isize = rec.get("isize", 0)
    optdeps = rec.get("optdepends", []) or []

    out = []
    # Header line: name is the anchor the viewer parses on.
    out.append(f"### {pkg}  ({version})")
    out.append("")
    # Purpose first -- this is the thing a human is here to read.
    out.extend(_wrap_field("purpose", desc))
    if url:
        out.append(f"upstream: {url}")
    out.append("")
    # Identity / classification.
    out.append(f"edition:  {EDITION_LABEL[tag['edition']]}")
    out.append(f"category: {tag['category']}")
    out.append(f"layer:    {layer} of {len(LAYER_ROLE) - 1}  ({LAYER_ROLE[layer]})")
    out.append(f"repo:     {repo}    installed size: {_fmt_size(isize)}    "
               f"license: {rec.get('license') or '(unknown)'}")
    # Az'arch-specific note, when present, is important enough to call out.
    if tag.get("azarch_note"):
        shipped = "REMOVED (not shipped on the ISO)" if tag.get("removed") \
            else "shipped, with Az'arch changes"
        out.extend(_wrap_field("az'arch", f"{tag['azarch_note']}  [{shipped}]"))
    out.append("")
    # Position in the graph: depth stats then the real edges.
    out.append(f"depth:    {tiers['trans_deps'][pkg]} pkgs pulled in below it "
               f"(transitively); {tiers['trans_dependents'][pkg]} pkgs above "
               f"rely on it")
    out.extend(_name_list(deps, "requires"))
    out.extend(_name_list(dependents, "required-by"))
    if optdeps:
        # Optional deps carry their own ': reason' text; keep each ENTIRELY on
        # one line (no hard-wrap) so it stays one logical record -- the terminal
        # or the viewer soft-wraps long ones. Hard-wrapping here would split a
        # single optdep across physical lines and be mis-read as two entries.
        out.append("optional:")
        for od in optdeps:
            out.append(f"    {od}")
    return out


def _index_block(order, packages, tags):
    """A compact grep-friendly index of every component, one line each."""
    out = [RULE, "COMPONENT INDEX", THIN,
           "Every component, one line: name, edition, category, version.",
           "Search this section to jump; full entries follow below.", ""]
    name_w = max((len(p) for p in order), default=4)
    for pkg in order:
        tag = tags[pkg]
        ed = EDITION_SHORT[tag["edition"]]
        ver = packages.get(pkg, {}).get("version", "?")
        out.append(f"  {pkg.ljust(name_w)}  {ed:8}  "
                   f"{tag['category'][:26]:26}  {ver}")
    out.append("")
    return out


def render_fulltext(packages, resolved, tiers, tags, glance, svg_rel, general_rel):
    """Return the complete component listing as plain text.

    Components are grouped by dependency layer (kernel at the bottom up to leaf
    apps), and within a layer sorted by how load-bearing they are (most-depended-
    on first), so reading top-to-bottom walks the stack the way it is built.
    """
    closure = resolved["closure"]
    heights = tiers["heights"]

    # Bucket into the 7 layers, same mapping the SVG uses.
    layers = [[] for _ in LAYER_ROLE]
    for p in closure:
        layers[_layer_of(p, tags[p]["category"], heights[p])].append(p)

    trans_dep = tiers["trans_dependents"]
    for i, band in enumerate(layers):
        # most load-bearing first, then alphabetical for stability
        band.sort(key=lambda p: (-trans_dep[p], p))

    # Global order for the index: bottom layer first, matching the body.
    order = [p for band in layers for p in band]

    lines = []
    w = lines.append

    # ---- title / header ------------------------------------------------- #
    w(RULE)
    w("AZ'ARCH -- FULL COMPONENT SPECIFICATION")
    w(RULE)
    w("")
    w("Every single component of the distribution, fully expanded -- nothing")
    w("collapsed. For each package: what it is (in plain language), which")
    w("layer of the stack it sits in, what it depends on, and what depends on")
    w("it. This is the exhaustive companion to:")
    w(f"  - {svg_rel}   (the at-a-glance layered graph)")
    w(f"  - {general_rel}   (prose + subsystem breakdown)")
    w("")
    w("The plain-language 'purpose' of each component is the official Arch")
    w("package description (the %DESC% field from the core/extra/multilib")
    w("package databases -- the same text archlinux.org and `pacman -Si` show),")
    w("with the upstream project URL. It is read straight from the package data,")
    w("so it is real and never drifts. For an interactive, clickable version of")
    w("this data, open SPECIFICATIONS_COMPONENTS_NAVIGATE_FULL.html in a browser.")
    w("")

    # ---- at a glance ---------------------------------------------------- #
    w(THIN)
    w("AT A GLANCE")
    w(THIN)
    facts = [
        ("Base", glance["base"]),
        ("Desktop", glance["desktop"]),
        ("Kernel", f'linux {glance["kernel"]}'),
        ("Init", f'systemd {glance["init"]}'),
        ("Live-session writable RAM", glance["ram"]),
        ("Packages (full closure)", str(glance["closure"])),
        ("  from core / extra / multilib",
         f'{glance["by_repo"]["core"]} / {glance["by_repo"]["extra"]} / '
         f'{glance["by_repo"]["multilib"]}'),
        ("Az'arch Component / Stock Arch",
         f'{glance["azarch"]} / {glance["stock"]}'),
        ("Deepest dependency chain", f'{glance["max_height"]} hops (leaf -> base)'),
        ("Total installed size", glance["size"]),
    ]
    for k, v in facts:
        w(f"  {k.ljust(42)} {v}")
    w("")

    # ---- legend --------------------------------------------------------- #
    w(THIN)
    w("HOW TO READ AN ENTRY")
    w(THIN)
    w("  ### name (version)")
    w("  purpose:     what it is, in plain language (from the Arch package DB)")
    w("  upstream:    the project's home page")
    w("  edition:     one of --")
    for ed in ("az'arch", "stock"):
        w(f"                 {EDITION_LABEL[ed]}")
    w("  category:    a single human-language role")
    w("  layer:       0 (sinks) .. 6 (leaf apps) -- real dependency depth")
    w("  requires:    the packages it directly depends on")
    w("  required-by: the packages in the set that directly depend on it")
    w("  optional:    optional deps and the capability each one adds")
    w("")

    # ---- index ---------------------------------------------------------- #
    lines.extend(_index_block(order, packages, tags))

    # ---- full entries, grouped by layer (top of stack drawn first so the
    #      file reads applications-down, matching how people think) -------- #
    for idx in reversed(range(len(LAYER_ROLE))):
        band = layers[idx]
        w(RULE)
        w(f"LAYER {idx} -- {LAYER_ROLE[idx]}")
        w(f"{len(band)} component(s)")
        w(RULE)
        w("")
        for pkg in band:
            lines.extend(_component_block(pkg, packages, resolved, tiers, tags))
            w("")
            w(THIN)
            w("")

    return "\n".join(lines) + "\n"
