"""Builds dark_mode.svg and light_mode.svg (neofetch-style profile card).

Runs daily from .github/workflows/build.yaml. Pulls live GitHub stats over the
GraphQL API and re-renders both cards from the ASCII portraits in art/.
"""
import datetime
import os
import time
from xml.sax.saxutils import escape

import requests
from dateutil import relativedelta

USER_NAME = os.environ.get('USER_NAME', 'emreyoleridev')
TOKEN = os.environ['ACCESS_TOKEN']
HEADERS = {'Authorization': f'bearer {TOKEN}'}
GITHUB_SINCE = datetime.datetime(2021, 6, 17)  # account creation date
WIDTH = 60  # characters per info line, dots fill the gap

INFO = [
    ('header', 'emre@yoleri'),
    ('OS', 'macOS, Ubuntu, ROS 2'),
    ('Uptime', None),  # time since joining GitHub
    ('Host', 'Politecnico di Torino'),
    ('Kernel', 'Robotics & Computer Vision Engineer'),
    ('IDE', 'VS Code, Jupyter'),
    ('blank',),
    ('Languages.Programming', 'Python, C++, SQL, Bash'),
    ('Languages.Computer', 'Markdown, YAML, JSON, URDF'),
    ('Languages.Real', 'Turkish, English'),
    ('blank',),
    ('Hobbies.Software', 'Teaching ML on YouTube'),
    ('Hobbies.Hardware', 'Robots, Simulation, Sensors'),
    ('section', 'Contact'),
    ('Website', 'emreyoleri.dev'),
    ('YouTube', '@emreyoleridev'),
    ('LinkedIn', 'emreyoleridev'),
    ('X', '@emreyoleridev'),
    ('Medium', '@emreyoleri'),
    ('section', 'GitHub Stats'),
    ('stats',),
]

THEMES = {
    'dark': dict(bg='#161b22', fg='#c9d1d9', key='#ffa657', value='#a5d6ff',
                 add='#3fb950', dele='#f85149', cc='#616e7f'),
    'light': dict(bg='#f6f8fa', fg='#24292f', key='#953800', value='#0a3069',
                  add='#1a7f37', dele='#cf222e', cc='#c2cfde'),
}


# ---------------------------------------------------------------- GitHub API
def gql(query, variables):
    for attempt in range(5):
        r = requests.post('https://api.github.com/graphql',
                          json={'query': query, 'variables': variables}, headers=HEADERS)
        if r.status_code == 200 and 'errors' not in r.json():
            return r.json()['data']
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'GraphQL failed: {r.status_code} {r.text[:300]}')


def user_info():
    q = '''query($login:String!){ user(login:$login){ id createdAt followers{totalCount} } }'''
    u = gql(q, {'login': USER_NAME})['user']
    return u['id'], u['createdAt'], u['followers']['totalCount']


def repos(affiliations):
    q = '''query($login:String!,$aff:[RepositoryAffiliation],$cursor:String){
      user(login:$login){ repositories(first:100, after:$cursor, ownerAffiliations:$aff){
        totalCount pageInfo{hasNextPage endCursor}
        nodes{ nameWithOwner isFork stargazerCount } } } }'''
    out, cursor = [], None
    while True:
        r = gql(q, {'login': USER_NAME, 'aff': affiliations, 'cursor': cursor})['user']['repositories']
        out += r['nodes']
        if not r['pageInfo']['hasNextPage']:
            return r['totalCount'], out
        cursor = r['pageInfo']['endCursor']


def commit_total(created_at):
    q = '''query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
      contributionsCollection(from:$from,to:$to){ totalCommitContributions restrictedContributionsCount } } }'''
    start = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    now = datetime.datetime.now(datetime.timezone.utc)
    total = 0
    while start < now:
        end = min(start + datetime.timedelta(days=365), now)
        c = gql(q, {'login': USER_NAME, 'from': start.isoformat(), 'to': end.isoformat()})
        c = c['user']['contributionsCollection']
        total += c['totalCommitContributions'] + c['restrictedContributionsCount']
        start = end
    return total


def loc(repo_list, owner_id):
    q = '''query($owner:String!,$name:String!,$author:ID!,$cursor:String){
      repository(owner:$owner,name:$name){ defaultBranchRef{ target{ ... on Commit{
        history(first:100, after:$cursor, author:{id:$author}){
          pageInfo{hasNextPage endCursor} nodes{ additions deletions } } } } } } }'''
    add = dele = 0
    for repo in repo_list:
        if repo['isFork']:
            continue
        owner, name = repo['nameWithOwner'].split('/')
        cursor = None
        while True:
            d = gql(q, {'owner': owner, 'name': name, 'author': owner_id, 'cursor': cursor})
            ref = d['repository']['defaultBranchRef']
            if not ref:
                break
            h = ref['target']['history']
            for n in h['nodes']:
                add += n['additions']
                dele += n['deletions']
            if not h['pageInfo']['hasNextPage']:
                break
            cursor = h['pageInfo']['endCursor']
    return add, dele


def uptime(birthday):
    d = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    p = lambda n, unit: f'{n} {unit}{"s" if n != 1 else ""}'
    s = f'{p(d.years, "year")}, {p(d.months, "month")}, {p(d.days, "day")}'
    return s


# ---------------------------------------------------------------- rendering
def t(cls, text, extra=''):
    return f'<tspan class="{cls}"{extra}>{escape(text)}</tspan>'


def dots(n):
    return ' ' + '.' * max(n, 1) + ' ' if n > 0 else ' '


def kv_line(key, value):
    """'. Key.Sub: ....... value' padded to WIDTH characters."""
    parts = key.split('.')
    key_len = sum(len(k) for k in parts) + len(parts) - 1
    gap = WIDTH - 2 - key_len - 1 - len(value) - 2
    keys = '.'.join(t('key', k) for k in parts)
    return f'{keys}:{t("cc", dots(gap))}{t("value", value)}'


def rule(label):
    return f'{escape(label)}</tspan> -{"—" * (WIDTH - len(label) - 5)}-—-'


def stats_lines(s):
    f = lambda n: f'{n:,}'
    # line 1: Repos: .... N {Contributed: N} | Stars: ..... N
    left = f'. Repos: {f(s["repos"])} {{Contributed: {f(s["contrib"])}}}'
    right = f'| Stars: {f(s["stars"])}'
    g1 = 30 - len(left) - 2
    g2 = WIDTH - 30 - len(right) - 2
    l1 = (f'{t("key", "Repos")}:{t("cc", dots(g1))}{t("value", f(s["repos"]))} '
          f'{{{t("key", "Contributed")}: {t("value", f(s["contrib"]))}}} | '
          f'{t("key", "Stars")}:{t("cc", dots(g2))}{t("value", f(s["stars"]))}')
    left = f'. Commits: {f(s["commits"])}'
    right = f'| Followers: {f(s["followers"])}'
    g1 = 30 - len(left) - 2
    g2 = WIDTH - 30 - len(right) - 2
    l2 = (f'{t("key", "Commits")}:{t("cc", dots(g1))}{t("value", f(s["commits"]))} | '
          f'{t("key", "Followers")}:{t("cc", dots(g2))}{t("value", f(s["followers"]))}')
    total = f'{f(s["add"] - s["del"])}'
    tail = f' ( {f(s["add"])}++, {f(s["del"])}-- )'
    g = WIDTH - len('. Lines of Code on GitHub:') - len(total) - len(tail) - 2
    l3 = (f'{t("key", "Lines of Code on GitHub")}:{t("cc", dots(g))}{t("value", total)}'
          f' ( {t("addColor", f(s["add"]))}{t("addColor", "++")}, '
          f'{t("delColor", f(s["del"]))}{t("delColor", "--")} )')
    return [l1, l2, l3]


def render(theme, art, s):
    c = THEMES[theme]
    w, h = 985, 530
    out = [f'''<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" width="{w}px" height="{h}px" font-size="16px">
<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.key {{fill: {c['key']};}}
.value {{fill: {c['value']};}}
.addColor {{fill: {c['add']};}}
.delColor {{fill: {c['dele']};}}
.cc {{fill: {c['cc']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{w}px" height="{h}px" fill="{c['bg']}" rx="15"/>
<text x="15" y="30" fill="{c['fg']}" class="ascii">''']
    for i, line in enumerate(art):
        out.append(f'<tspan x="15" y="{30 + 20 * i}">{escape(line)}</tspan>')
    out.append('</text>')
    out.append(f'<text x="390" y="30" fill="{c["fg"]}">')
    y = 30
    for item in INFO:
        kind = item[0]
        if kind == 'header':
            out.append(f'<tspan x="390" y="{y}">{rule(item[1])}')
        elif kind == 'section':
            y += 20  # empty line before each section
            out.append(f'<tspan x="390" y="{y}">- {rule(item[1])}')
        elif kind == 'blank':
            out.append(f'<tspan x="390" y="{y}" class="cc">. </tspan>')
        elif kind == 'stats':
            for i, line in enumerate(stats_lines(s)):
                out.append(f'<tspan x="390" y="{y + 20 * i}" class="cc">. </tspan>{line}')
        else:
            value = item[1] if item[1] is not None else s['uptime']
            out.append(f'<tspan x="390" y="{y}" class="cc">. </tspan>{kv_line(kind, value)}')
        y += 20
    out.append('</text>\n</svg>\n')
    return '\n'.join(out)


def main():
    owner_id, created_at, followers = user_info()
    n_owned, owned = repos(['OWNER'])
    n_aff, affiliated = repos(['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    add, dele = loc(affiliated, owner_id)
    s = dict(
        uptime=uptime(GITHUB_SINCE), repos=n_owned, contrib=n_aff, followers=followers,
        stars=sum(r['stargazerCount'] for r in owned), commits=commit_total(created_at),
        add=add, **{'del': dele},
    )
    print(s)
    here = os.path.dirname(os.path.abspath(__file__))
    for theme in THEMES:
        with open(os.path.join(here, 'art', f'{theme}.txt')) as f:
            art = f.read().rstrip('\n').split('\n')
        with open(os.path.join(here, f'{theme}_mode.svg'), 'w') as f:
            f.write(render(theme, art, s))


if __name__ == '__main__':
    main()
