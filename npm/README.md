# Panopticon npm packages

`@brnyxx/panopticon` is the public npm package. It provides the `pano` command and selects an exact-version native optional dependency for Linux glibc x64/arm64 and macOS x64/arm64.

The native packages are release artifacts, not general-purpose packages. They contain the retained `pano` executable unchanged. Linux packages require glibc; musl-based Linux is unsupported.

The launcher performs no download, network access, install lifecycle action, update check, shell evaluation, or persistence. If npm omitted the platform package, reinstall on a supported platform and ensure optional dependencies are enabled.
