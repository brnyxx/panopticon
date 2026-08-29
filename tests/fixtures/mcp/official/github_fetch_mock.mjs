const user = {
  login: 'fixture', id: 1, avatar_url: 'https://fixture.invalid',
  url: 'https://fixture.invalid', html_url: 'https://fixture.invalid',
};
const owner = { ...user, node_id: 'node', type: 'User' };
const repository = {
  id: 1, node_id: 'node', name: 'fixture', full_name: 'fixture/repository', private: false,
  owner, html_url: 'https://fixture.invalid', description: null, fork: false,
  url: 'https://fixture.invalid', created_at: '2026-01-01', updated_at: '2026-01-01',
  pushed_at: '2026-01-01', git_url: 'git://fixture', ssh_url: 'ssh://fixture',
  clone_url: 'https://fixture.invalid', default_branch: 'main',
};
const reference = {
  ref: 'refs/heads/main', node_id: 'node', url: 'https://fixture.invalid',
  object: { sha: 'abc', type: 'commit', url: 'https://fixture.invalid' },
};
const author = { name: 'fixture', email: 'fixture@example.test', date: '2026-01-01' };
const file = {
  name: 'fixture', path: 'fixture', sha: 'abc', size: 1, url: 'https://fixture.invalid',
  html_url: 'https://fixture.invalid', git_url: 'https://fixture.invalid',
  download_url: 'https://fixture.invalid', type: 'file', content: 'eA==', encoding: 'base64',
  _links: { self: 'https://fixture.invalid', git: null, html: null },
};
const commit = {
  sha: 'abc', node_id: 'node', url: 'https://fixture.invalid', author, committer: author,
  message: 'fixture', tree: { sha: 'abc', url: 'https://fixture.invalid' }, parents: [],
};
const pullRef = { label: 'fixture', ref: 'fixture', sha: 'abc', user, repo: repository };
const pull = {
  url: 'https://fixture.invalid', id: 1, node_id: 'node', html_url: 'https://fixture.invalid',
  diff_url: 'https://fixture.invalid', patch_url: 'https://fixture.invalid',
  issue_url: 'https://fixture.invalid', number: 1, state: 'open', locked: false,
  title: 'fixture', user, body: null, created_at: '2026-01-01', updated_at: '2026-01-01',
  closed_at: null, merged_at: null, merge_commit_sha: null, assignee: null, assignees: [],
  requested_reviewers: [], labels: [], head: pullRef, base: pullRef,
};
const review = {
  id: 1, node_id: 'node', user, body: null, state: 'COMMENTED',
  html_url: 'https://fixture.invalid', pull_request_url: 'https://fixture.invalid',
  commit_id: 'abc', submitted_at: null, author_association: 'NONE',
};
const response = (value) => new Response(JSON.stringify(value), {
  status: 200, headers: { 'content-type': 'application/json' },
});
globalThis.fetch = async (input, options = {}) => {
  const url = String(input);
  const method = options.method || 'GET';
  if (url.includes('/search/repositories')) {
    return response({ total_count: 0, incomplete_results: false, items: [] });
  }
  if (url.includes('/contents/')) {
    return response(method === 'PUT'
      ? { content: file, commit: { ...commit, html_url: 'https://fixture.invalid' } }
      : file);
  }
  if (url.includes('/git/trees')) {
    return response({ sha: 'abc', url: 'https://fixture.invalid', tree: [], truncated: false });
  }
  if (url.includes('/git/commits')) return response(commit);
  if (url.includes('/git/refs')) return response(reference);
  if (url.includes('/commits/') && url.endsWith('/status')) {
    return response({ state: 'success', statuses: [], sha: 'abc', total_count: 0 });
  }
  if (url.includes('/pulls/') && url.endsWith('/reviews')) {
    return response(method === 'POST' ? review : []);
  }
  if (url.includes('/pulls/') && (url.endsWith('/comments') || url.endsWith('/files'))) {
    return response([]);
  }
  if (/\/pulls\/[^/?]+$/.test(url)) return response(pull);
  if (/\/pulls(\?|$)/.test(url)) return response(method === 'POST' ? pull : []);
  if (url.endsWith('/forks') || url.includes('/forks?')) {
    return response({ ...repository, parent: repository, source: repository });
  }
  if (url.endsWith('/user/repos')) return response(repository);
  return response({});
};
