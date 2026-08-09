"""
3141roy/3141roy — profile card updater.

Walks the GitHub GraphQL API for repo/star/follower counts and commit
totals, then for each of your own commits pulls per-file additions/
deletions via REST (GraphQL has no per-file breakdown) and sums them,
skipping datasets and gitignore-typical build/cache dirs (see
EXCLUDED_EXTENSIONS / EXCLUDED_DIR_PARTS) so committed CSVs, __pycache__,
etc. don't inflate the Lines of Code stat. Results are written into
dark_mode.svg / light_mode.svg by id lookup. Per-repo results are cached
in cache/<hash>.txt so unchanged repos aren't re-walked on every run.

Alignment: every stat row right-justifies to TOTAL_WIDTH characters (same
rule the SVG template was built with — see build_svg.py in this repo's
history / the comment in that file for how it was derived). Dots are
recomputed each run from the FULL rendered row, so the row never drifts
out of alignment as numbers grow digits.

Requires env vars ACCESS_TOKEN (fine-grained PAT, read-only repo+account
scopes, must include private repos if you want those counted) and
USER_NAME. EXCLUDED_OWNERS is optional, comma-separated (e.g.
"SomeOrg,SomeUser") — repos under those owners are dropped from the
contributed-repo/LOC stats entirely. Run by .github/workflows/build.yaml
on a daily cron.
"""

import datetime
import hashlib
import os
import time

import requests
from dateutil import relativedelta
from lxml import etree

API_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"
HEADERS = {"authorization": "token " + os.environ["ACCESS_TOKEN"]}
REST_HEADERS = {**HEADERS, "Accept": "application/vnd.github+json"}
USER_NAME = os.environ["USER_NAME"]
CACHE_DIR = "cache"

BIRTHDAY = datetime.datetime(2002, 6, 5)  # for the Uptime row
TOTAL_WIDTH = 58  # must match build_svg.py — keeps rows right-justified
BULLET = ". "

CALL_COUNT = {}

# Files/dirs excluded from the LOC count: datasets and other generated/
# vendored content that shouldn't count as "written" lines even if they
# ended up committed (e.g. a .gitignore added after the fact).
EXCLUDED_EXTENSIONS = {
    ".csv", ".tsv", ".parquet", ".pkl", ".pickle", ".pyc", ".pyo",
    ".so", ".dll", ".class", ".jar", ".db", ".sqlite", ".sqlite3",
    ".zip", ".tar", ".gz", ".7z", ".log",
}
EXCLUDED_DIR_PARTS = {
    "__pycache__", "node_modules", ".venv", "venv", "env", ".env",
    "dist", "build", ".ipynb_checkpoints", ".pytest_cache", ".mypy_cache", ".tox",
}

# Orgs whose repos shouldn't count toward "contributed" stats at all (e.g.
# access granted for review/audit, not actual authorship). Kept out of
# source (public repo) — comma-separated in the EXCLUDED_OWNERS secret.
EXCLUDED_OWNERS = {o.strip() for o in os.environ.get("EXCLUDED_OWNERS", "").split(",") if o.strip()}


def is_excluded(filename):
    """True if filename shouldn't count toward LOC — data files or a
    build/cache/vendor directory that normally lives in .gitignore."""
    parts = filename.split("/")
    for part in parts[:-1]:
        if part in EXCLUDED_DIR_PARTS or part.endswith(".egg-info"):
            return True
    ext = os.path.splitext(parts[-1])[1].lower()
    return ext in EXCLUDED_EXTENSIONS


def gql(query, variables, tag):
    CALL_COUNT[tag] = CALL_COUNT.get(tag, 0) + 1
    resp = requests.post(API_URL, json={"query": query, "variables": variables}, headers=HEADERS)
    if resp.status_code != 200:
        raise RuntimeError(f"{tag} failed: {resp.status_code} {resp.text}")
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(f"{tag} returned errors: {payload['errors']}")
    return payload["data"]


def author_node_id(username):
    data = gql(
        "query($login: String!) { user(login: $login) { id } }",
        {"login": username},
        "author_node_id",
    )
    return data["user"]["id"]


def follower_count(username):
    data = gql(
        "query($login: String!) { user(login: $login) { followers { totalCount } } }",
        {"login": username},
        "follower_count",
    )
    return data["user"]["followers"]["totalCount"]


def age_string(birthday):
    """'X years, Y months, Z days' since birthday — the Uptime row."""
    diff = relativedelta.relativedelta(datetime.datetime.utcnow(), birthday)

    def unit(n, word):
        return f"{n} {word}{'s' if n != 1 else ''}"

    return f"{unit(diff.years, 'year')}, {unit(diff.months, 'month')}, {unit(diff.days, 'day')}"


def repo_page_with_commit_totals(owner_affiliation, include_stars):
    """
    All repos for the given affiliation, paginated, each stamped with its
    default-branch commit totalCount. `stargazers` is only requested for
    owned repos (include_stars=True) — on repos you're a collaborator/org
    member on but don't own, a fine-grained PAT can get a FORBIDDEN back
    for that field unless the org has explicitly approved the token, even
    with read access to the repo itself. We never need star counts for
    non-owned repos anyway, so just don't ask.
    """
    star_field = "stargazers { totalCount }" if include_stars else ""
    edges, cursor, total = [], None, None
    while True:
        data = gql(
            f"""
            query($aff: [RepositoryAffiliation], $login: String!, $cursor: String) {{
                user(login: $login) {{
                    repositories(first: 60, after: $cursor, ownerAffiliations: $aff, isFork: false) {{
                        totalCount
                        edges {{
                            node {{
                                nameWithOwner
                                {star_field}
                                defaultBranchRef {{
                                    target {{ ... on Commit {{ history {{ totalCount }} }} }}
                                }}
                            }}
                        }}
                        pageInfo {{ endCursor hasNextPage }}
                    }}
                }}
            }}""",
            {"aff": owner_affiliation, "login": USER_NAME, "cursor": cursor},
            "repo_page_with_commit_totals",
        )
        page = data["user"]["repositories"]
        total = page["totalCount"]
        for e in page["edges"]:
            ref = e["node"]["defaultBranchRef"]
            e["node"]["_history_total_count"] = ref["target"]["history"]["totalCount"] if ref else 0
        edges += page["edges"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return total, edges


def total_stars(edges):
    return sum(e["node"]["stargazers"]["totalCount"] for e in edges)


def commit_history_page(owner, repo, cursor=None):
    data = gql(
        """
        query($owner: String!, $repo: String!, $cursor: String) {
            repository(owner: $owner, name: $repo) {
                defaultBranchRef {
                    target {
                        ... on Commit {
                            history(first: 100, after: $cursor) {
                                edges {
                                    node { oid additions deletions author { user { id } } }
                                }
                                pageInfo { endCursor hasNextPage }
                            }
                        }
                    }
                }
            }
        }""",
        {"owner": owner, "repo": repo, "cursor": cursor},
        "commit_history_page",
    )
    ref = data["repository"]["defaultBranchRef"]
    return ref["target"]["history"] if ref else None


def commit_file_stats(owner, repo, sha):
    """Per-file additions/deletions for one commit via REST (GraphQL has no
    per-file breakdown), summed after dropping excluded files. Follows the
    Link header for commits with enough changed files to paginate."""
    additions = deletions = 0
    url = f"{REST_URL}/repos/{owner}/{repo}/commits/{sha}"
    while url:
        resp = requests.get(url, headers=REST_HEADERS)
        CALL_COUNT["commit_file_stats"] = CALL_COUNT.get("commit_file_stats", 0) + 1
        if resp.status_code != 200:
            raise RuntimeError(f"commit_file_stats failed: {resp.status_code} {resp.text}")
        for f in resp.json().get("files", []):
            if not is_excluded(f["filename"]):
                additions += f["additions"]
                deletions += f["deletions"]
        url = resp.links.get("next", {}).get("url")
    return additions, deletions


def walk_repo_commits(owner, repo, author_id):
    """Paginate a repo's default-branch history, summing LOC/commits authored by author_id."""
    additions = deletions = mine = 0
    cursor = None
    while True:
        history = commit_history_page(owner, repo, cursor)
        if history is None:
            return additions, deletions, mine
        for edge in history["edges"]:
            node = edge["node"]
            if node["author"]["user"] and node["author"]["user"]["id"] == author_id:
                mine += 1
                add, delete = commit_file_stats(owner, repo, node["oid"])
                additions += add
                deletions += delete
        if not history["pageInfo"]["hasNextPage"]:
            return additions, deletions, mine
        cursor = history["pageInfo"]["endCursor"]


def cache_path():
    os.makedirs(CACHE_DIR, exist_ok=True)
    digest = hashlib.sha256(USER_NAME.encode()).hexdigest()
    # loc_ prefix so .gitignore can target just this generated file —
    # persisted via actions/cache in the workflow, never committed.
    return os.path.join(CACHE_DIR, f"loc_{digest}.txt")


def load_cache():
    """repo_full_name -> (commit_total_seen, my_commits, additions, deletions)"""
    path = cache_path()
    if not os.path.exists(path):
        return {}
    cache = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 5:
                continue
            name, total, mine, add, delete = parts
            cache[name] = (int(total), int(mine), int(add), int(delete))
    return cache


def save_cache(cache):
    with open(cache_path(), "w") as f:
        for name, (total, mine, add, delete) in sorted(cache.items()):
            f.write(f"{name} {total} {mine} {add} {delete}\n")


def loc_and_commits(author_id, edges, cache):
    """
    Use each repo's current default-branch commit count as a change
    detector: if it matches the cached value, reuse cached LOC/commit
    numbers instead of re-walking that repo's whole history.
    """
    add_total = del_total = commit_total = 0
    for e in edges:
        name = e["node"]["nameWithOwner"]
        owner, repo = name.split("/", 1)
        current_total = e["node"]["_history_total_count"]
        cached = cache.get(name)
        if cached and cached[0] == current_total:
            _, mine, add, delete = cached
        else:
            add, delete, mine = walk_repo_commits(owner, repo, author_id)
            cache[name] = (current_total, mine, add, delete)
        add_total += add
        del_total += delete
        commit_total += mine
    return add_total, del_total, commit_total


def dot_run(just_len):
    """Same special-casing the SVG template was built with (see build_svg.py):
    very short gaps skip the dots entirely rather than rendering one lonely '.'."""
    if just_len <= 0:
        return ""
    if just_len == 1:
        return " "
    if just_len == 2:
        return ". "
    return " " + ("." * (just_len - 2)) + " "


def set_text(root, element_id, text):
    node = root.find(f".//*[@id='{element_id}']")
    if node is not None:
        node.text = text


def get_text(root, element_id):
    node = root.find(f".//*[@id='{element_id}']")
    return node.text or "" if node is not None else ""


def right_justify_row(root, dots_id, label, value_ids_and_texts, static_suffix_len=0):
    """
    Sets every value_id's text, then recomputes dots_id so the WHOLE row
    (label + dots + all values + any static connector text already baked
    into the template, e.g. ' {Contributed: ' or ' | Followers: ') totals
    TOTAL_WIDTH chars — same rule build_svg.py used, so live edits never
    drift out of alignment with the rows that don't change.
    """
    for element_id, text in value_ids_and_texts:
        set_text(root, element_id, text)
    prefix_len = len(BULLET) + len(label) + 1  # +1 for ':'
    values_len = sum(len(text) for _, text in value_ids_and_texts)
    dots = dot_run(TOTAL_WIDTH - prefix_len - values_len - static_suffix_len)
    set_text(root, dots_id, dots)


def write_svg(path, stats):
    tree = etree.parse(path)
    root = tree.getroot()

    right_justify_row(root, "uptime_data_dots", "Uptime", [("uptime_data", stats["uptime"])])

    # "Repos: .... 21 {Contributed: 21} | Stars: .... 1"
    # static connector text already in the template: " {Contributed: " + "} | Stars: "
    static = len(" {Contributed: ") + len("} | Stars: ")
    right_justify_row(
        root, "repo_data_dots", "Repos",
        [("repo_data", f"{stats['repos']:,}"),
         ("contrib_data", f"{stats['contributed']:,}"),
         ("star_data", f"{stats['stars']:,}")],
        static_suffix_len=static,
    )

    # "Commits: ... 123 | Followers: .... 8"
    static = len(" | Followers: ")
    right_justify_row(
        root, "commit_data_dots", "Commits",
        [("commit_data", f"{stats['commits']:,}"),
         ("follower_data", f"{stats['followers']:,}")],
        static_suffix_len=static,
    )

    # "Lines of Code on GitHub: 123 ( 456++, 78-- )"
    static = len(" ( ") + len("++") + len(", ") + len("--") + len(" )")
    right_justify_row(
        root, "loc_data_dots", "Lines of Code on GitHub",
        [("loc_data", f"{stats['loc_net']:,}"),
         ("loc_add", f"{stats['loc_add']:,}"),
         ("loc_del", f"{stats['loc_del']:,}")],
        static_suffix_len=static,
    )

    set_text(root, "synced_data", stats["synced"])
    tree.write(path, encoding="utf-8", xml_declaration=True)


def timed(label, fn, *args):
    start = time.perf_counter()
    result = fn(*args)
    print(f"  {label:<28}{time.perf_counter() - start:8.3f}s")
    return result


if __name__ == "__main__":
    print("Updating profile card for", USER_NAME)

    author_id = timed("author_node_id", author_node_id, USER_NAME)
    followers = timed("follower_count", follower_count, USER_NAME)
    owned_count, owned_edges = timed("collect_repos(owned)", repo_page_with_commit_totals, ["OWNER"], True)
    contrib_count, contrib_edges = timed(
        "collect_repos(contributed)", repo_page_with_commit_totals,
        ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"], False,
    )
    contrib_edges = [e for e in contrib_edges if e["node"]["nameWithOwner"].split("/", 1)[0] not in EXCLUDED_OWNERS]
    contrib_count = len(contrib_edges)

    cache = load_cache()
    add_loc, del_loc, commits = timed("loc_and_commits", loc_and_commits, author_id, contrib_edges, cache)
    save_cache(cache)

    stats = {
        "uptime": age_string(BIRTHDAY),
        "repos": owned_count,
        "contributed": contrib_count,
        "commits": commits,
        "stars": total_stars(owned_edges),
        "followers": followers,
        "loc_add": add_loc,
        "loc_del": del_loc,
        "loc_net": add_loc - del_loc,
        "synced": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    write_svg("dark_mode.svg", stats)
    write_svg("light_mode.svg", stats)

    print("GraphQL calls:", sum(CALL_COUNT.values()), CALL_COUNT)
