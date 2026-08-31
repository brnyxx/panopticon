# Panopticon Demo Design

## Direction

The public demo uses the archived design direction `d13edae8`, **Decoy Lab**. The versioned
production sources are `site/template.html`, `site/assets/site.css`, and `site/assets/logo.svg`;
local design-review tool state is not part of the shipped surface.

The page treats observation as a lab record rather than a product verdict. Deep navy space,
concentric trace rings, one orange observation pupil, thin keylines, and mono evidence labels form
the visual language. The first desktop viewport retains the asymmetric copy/ledger composition;
later sections reuse the same evidence grammar without imitating a dashboard. The ledger mark is
drawn from the keyline system rather than borrowed from a platform glyph, and one bounded aperture
lock supplies the page's only authored entrance moment. Directional marks are authored from the
same one- and two-pixel CSS strokes; platform arrow glyphs are not part of the interface.

## Brand promise

The product promise is **“We don't watch you. We watch your MCPs.”** The first viewport names MCPs,
shows one explicitly selected fixture target entering a generated decoy runtime, and ends in an
inspectable evidence record. Within ten seconds a visitor must find:

1. Files, network, and process evidence with exhaustive stage states.
2. One clearly labeled illustrative decoy-marker finding with its stable rule ID.
3. The exact install, doctor, and watch route plus “Not observed is not a pass.”

The promise is not a fear device. Human eyes, prisons, cells, watchtowers, robots, red-alert
theater, shields, locks, scores, seals, and “caught” language are prohibited. Product diagrams draw
only observable runtime boundaries and evidence the implementation actually records.

## Tokens

- Background: `#010714`
- Raised surface: `#071022`, `#0b1428`
- Keylines: `#1d2b43`, `#40536e`
- Observation rings: `#42587b`, `#6b7eb0`
- Primary action: `#fb7c05`
- Secondary signal: `#f5b52b`
- Complete observation: `#67b376`
- Main text: `#f2f0ed`
- Secondary text: `#afb5c9`
- Heading face: Georgia/Times fallback
- Interface face: system sans
- Evidence and commands: system mono

Color never carries state alone. COMPLETE uses a circle, INCOMPLETE a square, UNSUPPORTED a
triangle, and UNKNOWN an outlined square, each paired with its text label and reason.

These values are canonical for browser and repository assets. SVGs do not carry alternate
`#FF7A1A`/`#0A0E1A` palettes or platform-dependent display faces. Structural rules render at one
pixel, emphasized rules at two pixels, and no published-size vector stroke may resolve below one
pixel.

## Asset system

The logo is a floor-plan aperture reduced to four durable shapes: a navy tile, one outer record
ring, one white iris, and one orange terminal-cursor pupil. Exactly one orange ring segment denotes
the explicitly selected MCP. The mark has no blur filter, detection dots, or secondary “caught”
cells and remains recognizable at 16, 32, 96, and 256 pixels. The repository and site SVGs are
byte-identical; the site also ships a local 32px PNG fallback.

The repository hero is a crisp product-flow diagram, not scene art: selected fixture target →
generated decoy runtime → evidence record. Text is high-contrast and labels the example
illustrative. README evidence imagery comes from the deterministic reporter over a sanitized
fixture. All social and browser assets are local, deterministic, and free of remote font or image
dependencies.

## Layout

At 1280px and wider, the first surface uses a 30/70 implementation of the approved asymmetric
composition so the measured ledger bounds align with the reference while preserving the intended
copy/evidence split. The copy measure remains narrow; the ledger owns the dominant reading area.

Below 1280px, copy and evidence stack. At 900px, the coverage rail moves below the ledger. At 767px
and below, sections use one column and navigation wraps. At 420px and below, command text remains on
one line inside its own horizontal scroller while the page itself does not scroll horizontally. The
primary install command uses a two-row instrument housing at every width so the exact release pin
has the full content measure instead of competing with its copy control.

## Information architecture

The page uses progressive disclosure without hiding prerequisites or consent boundaries:

1. MCP-specific promise and one bounded example observation with a decoy-marker signal.
2. Always-visible runtime, image-staging, and target-selection prerequisites.
3. The pinned three-command runway and validated public installation choices.
4. A uniquely titled evidence-dimensions section explaining what each collector can and cannot
   support, including the difference between stage status and an `UNKNOWN` conclusion.
5. A goal-oriented command map that names execution, network, and mutation boundaries.
6. A copyable agent protocol with human choice and reporting requirements.
7. Local evidence, privacy scope, detailed guides, and a final install action.

The runway remains the dominant first path. Installation alternatives, command breadth, and internal
design material appear below it so a first-time user can act quickly without losing the information
needed to operate the product deliberately.

## Interaction

The hero has one clipboard control inside the command housing. Clipboard denial selects the exact
command and announces localized manual guidance. Success is also announced through the existing
live region. State resets after two seconds and nothing is persisted. The dominant orange action is
a real navigation control that enters the prerequisite and runway path; its forward mark therefore
matches its behavior.

Observation dimensions use the WAI-ARIA tabs structure. Left/Right wrap between tabs; Home and End
move to the bounds. Inactive panels remain mounted and are excluded with `hidden`.

Language selection is static navigation: `/` for English and `/ko/` for Korean. It does not depend
on JavaScript or browser storage.

Every copy control has a command-specific accessible name and an associated live region. The
observation and command tables expose named horizontal-scroll regions. The agent prompt wraps as
prose rather than imitating a terminal command. The sticky header keeps language and route controls
reachable; its backdrop treatment exists only to preserve legibility over the measured surface.

## Documentation system

- `README.md` and `docs/README.ko.md` provide the same end-user spine.
- `docs/getting-started.md` and `docs/getting-started.ko.md` own installation, observation,
  interpretation, command choice, artifacts, cleanup, and troubleshooting.
- `docs/agent-guide.md` owns machine-operation defaults, human confirmation boundaries, exit-code
  handling, and a copyable instruction.
- `docs/release.md` contains only public installation, verification, upgrade, and rollback.
- `docs/release-maintainers.md` isolates build-once promotion, recovery, and human npm bootstrap.
- `ARCHITECTURE.md`, `docs/DECISIONS.md`, and `panopticon-buildplan.md` remain the engineering
  contracts behind the public experience.

## Accessibility and motion

Every control and navigation link has at least a 44px interaction target. Keyboard focus uses a
three-pixel amber outline with offset. The page includes a skip link, semantic landmarks, ordered
headings, explicit table headers, status text, and live regions.

Reduced-motion mode removes smooth scrolling, transitions, animations, and the tab indicator
transform through `@media (prefers-reduced-motion: reduce)`. No interaction relies on animation.
Selection, focus, scrollbars, tabular numerals, hover, active, and disabled control states inherit
the same evidence palette rather than browser-default styling.

The single authored motion sequence is the aperture locking onto the evidence ledger followed by
the four evidence states resolving once, in order, within 1.2 seconds. Nothing loops. The
observation pupil is anchored to the ledger frame rather than positioned from the copy column.

## Runtime boundary

The browser loads only the generated HTML and local CSS, JavaScript, and SVG. There is no analytics,
cookie, local storage, telemetry, or automatic remote request. GitHub and privacy URLs are ordinary
user-invoked navigation links; the footer separately identifies the GitHub Pages hosting policy.
The short “No telemetry” line is always paired with scoped product, installer, tested-MCP, optional
feature, and hosting boundaries.
