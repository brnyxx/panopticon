# `.panopticon.yaml` — maintainer self-declaration

Place at the root of your MCP repository. It is the highest-priority declared-scope source and the prerequisite for the `declared = observed` badge.

```yaml
version: 1
hosts: [api.github.com, "*.githubusercontent.com"]   # leading "*." wildcard only
paths: ["~/.gitconfig"]                               # globs, ~-relative
env: [GITHUB_TOKEN]
processes: [git]
notes: "gitconfig is read only to display the user name"
```

`pano watch --self --badge` produces `panopticon-badge.svg` when every observed event is covered by this declaration. The badge carries the observation date and never uses the words "safe" or "certified".
