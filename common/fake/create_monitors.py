import argparse
import asyncio
import sys

import httpx
from faker import Faker
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.db.db_init import get_database_url, load_env
from services.monitoring.constants import MAXIMUM_MONITORS
from services.monitoring.models import MonitorModel
from services.monitoring.schemas import MonitorCreate
from services.users.models import User


REAL_TARGETS = tuple(
    f"https://{host}/" for host in """
    www.python.org docs.python.org pypi.org www.djangoproject.com
    flask.palletsprojects.com fastapi.tiangolo.com www.starlette.io
    www.uvicorn.org www.sqlalchemy.org docs.sqlalchemy.org
    docs.pydantic.dev www.postgresql.org www.sqlite.org redis.io
    www.rabbitmq.com docs.celeryq.dev faker.readthedocs.io
    www.python-httpx.org www.python-requests.org www.aiohttp.org
    numpy.org pandas.pydata.org scipy.org matplotlib.org
    scikit-learn.org jupyter.org ipython.org www.sympy.org
    www.pillow.readthedocs.io www.sphinx-doc.org www.mkdocs.org
    packaging.python.org pytest.org docs.pytest.org
    www.rust-lang.org doc.rust-lang.org crates.io docs.rs
    go.dev pkg.go.dev golang.org nodejs.org www.npmjs.com
    www.typescriptlang.org www.javascript.com react.dev vuejs.org
    angular.dev svelte.dev nextjs.org nuxt.com vite.dev
    vitest.dev jestjs.io playwright.dev www.cypress.io
    expressjs.com fastify.dev deno.com bun.sh
    www.php.net www.ruby-lang.org www.ruby-lang.org/en/documentation
    rubyonrails.org www.perl.org www.lua.org www.haskell.org
    www.scala-lang.org kotlinlang.org www.java.com openjdk.org
    clojure.org elixir-lang.org www.erlang.org ziglang.org
    julialang.org dart.dev flutter.dev swift.org
    www.r-project.org www.gnu.org www.kernel.org www.linux.org
    www.debian.org ubuntu.com www.alpinelinux.org archlinux.org
    fedoraproject.org www.freebsd.org www.openbsd.org
    git-scm.com github.com gitlab.com codeberg.org
    www.docker.com docs.docker.com kubernetes.io helm.sh
    podman.io containerd.io ansible.com www.terraform.io
    opentofu.org www.pulumi.com caddyserver.com nginx.org
    httpd.apache.org tomcat.apache.org www.apache.org
    kafka.apache.org spark.apache.org arrow.apache.org
    flink.apache.org airflow.apache.org parquet.apache.org
    maven.apache.org gradle.org ant.apache.org
    prometheus.io grafana.com opentelemetry.io jaegertracing.io
    www.envoyproxy.io istio.io linkerd.io traefik.io
    www.w3.org www.ietf.org www.rfc-editor.org www.iana.org
    www.icann.org www.internetsociety.org www.mozilla.org
    developer.mozilla.org www.wikipedia.org en.wikipedia.org
    www.wikimedia.org commons.wikimedia.org www.wikidata.org
    www.mediawiki.org www.openstreetmap.org www.openlibrary.org
    archive.org www.gutenberg.org www.loc.gov www.si.edu
    www.nasa.gov science.nasa.gov www.noaa.gov www.weather.gov
    www.nist.gov www.nsf.gov www.usgs.gov www.census.gov
    www.epa.gov www.energy.gov home.cern www.esa.int
    www.un.org www.unesco.org www.unicef.org www.who.int
    www.worldbank.org www.imf.org www.oecd.org europa.eu
    www.europarl.europa.eu commission.europa.eu www.ecb.europa.eu
    www.bbc.com www.theguardian.com apnews.com www.npr.org
    www.reuters.com www.dw.com www.france24.com www.euronews.com
    www.nature.com www.science.org arxiv.org info.arxiv.org
    zenodo.org figshare.com www.doi.org www.crossref.org
    www.datacite.org www.ourworldindata.org www.gapminder.org
    www.khanacademy.org www.edx.org www.coursera.org ocw.mit.edu
    www.mit.edu www.stanford.edu www.harvard.edu www.ox.ac.uk
    www.cam.ac.uk www.princeton.edu www.berkeley.edu www.caltech.edu
    www.letsencrypt.org www.openssl.org curl.se www.wireshark.org
    nmap.org www.libreoffice.org www.documentfoundation.org
    www.blender.org www.gimp.org inkscape.org www.videolan.org
    www.audacityteam.org obsproject.com krita.org godotengine.org
    www.qemu.org www.virtualbox.org www.7-zip.org www.vim.org
    neovim.io code.visualstudio.com vscodium.com www.eclipse.org
    www.jetbrains.com www.sonarsource.com about.gitlab.com
    """.split()
)


BAD_TARGETS = (
    "https://httpbin.org/status/404",
    "https://httpbin.org/status/500",
    "https://httpbin.org/status/503",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Fill the first two users' accounts with real, HTTP-checked monitors.")
    parser.add_argument("--first-count", type=int, default=99, help="Target total for the first user (default: 99), including 3 failing URLs.")
    parser.add_argument("--second-count", type=int, default=100, help="Target total for the second user (default: 100), including 3 failing URLs.")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60).")
    parser.add_argument("--failure-threshold", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="Verify targets and report planned inserts without writing data.")
    args = parser.parse_args()
    for count in (args.first_count, args.second_count):
        if not len(BAD_TARGETS) <= count <= MAXIMUM_MONITORS:
            parser.error(f"Counts must be between {len(BAD_TARGETS)} and {MAXIMUM_MONITORS}")
    if not 5 <= args.interval <= 3600:
        parser.error("--interval must be between 5 and 3600")
    if not 1 <= args.failure_threshold <= 10:
        parser.error("--failure-threshold must be between 1 and 10")
    return args


async def resolve_users():
    engine = create_async_engine(get_database_url("users"))
    try:
        async with async_sessionmaker(engine)() as session:
            rows = (await session.execute(
                select(User.id, User.username)
                .order_by(User.created_at, User.id)
                .limit(2)
            )).all()
            if len(rows) != 2:
                raise ValueError("At least two users must exist in the database before running this script.")
            return {user_id: username for user_id, username in rows}
    finally:
        await engine.dispose()


async def checked_urls(count):
    verified = []
    seen = set()
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=10.0,
        headers={"User-Agent": "PingPatrol-MonitorSeeder/1.0"},
    ) as client:
        async def check(url):
            try:
                async with client.stream("GET", url) as response:
                    if 200 <= response.status_code < 300:
                        return str(response.url)
            except httpx.HTTPError:
                pass
            return None

        for offset in range(0, len(REAL_TARGETS), 6):
            results = await asyncio.gather(*(check(url) for url in REAL_TARGETS[offset:offset + 6]))
            for url in results:
                if url and url not in seen:
                    verified.append(url)
                    seen.add(url)
            print(f"[urls] Verified {len(verified)} distinct reachable URLs; need {count}.", flush=True)
            if len(verified) >= count:
                return verified[:count]
    raise ValueError(f"Only {len(verified)} real URLs responded with HTTP 2xx. Nothing was inserted; retry when connectivity is available.")


async def main(args, verified_urls=None):
    load_env()
    users = await resolve_users()
    targets = dict(zip(users, (args.first_count, args.second_count)))
    engine = create_async_engine(get_database_url("monitoring"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    fake = Faker()
    try:
        async with sessions() as session:
            rows = (await session.execute(select(MonitorModel.owner_id, MonitorModel.url).where(MonitorModel.owner_id.in_(users)))).all()
        current_urls = {user_id: [] for user_id in users}
        for owner_id, url in rows:
            current_urls[owner_id].append(url)
        for user_id, username in users.items():
            missing_bad = len(set(BAD_TARGETS) - set(current_urls[user_id]))
            if missing_bad > max(0, targets[user_id] - len(current_urls[user_id])):
                raise ValueError(f"{username}: not enough free slots for the three failing monitors; existing records were not modified.")
        if all(len(current_urls[user_id]) >= targets[user_id] for user_id in users):
            for user_id, username in users.items():
                print(f"[{username}] Already has {len(current_urls[user_id])} monitors, including all 3 failing URLs; skipped.")
            return

        good_count = max(targets.values()) - len(BAD_TARGETS)
        urls = verified_urls if verified_urls is not None else await checked_urls(good_count)
        plans = []
        async with sessions() as session, session.begin():
            for user_id, username in users.items():
                current = (await session.execute(select(MonitorModel.url).where(MonitorModel.owner_id == user_id))).scalars().all()
                needed = max(0, targets[user_id] - len(current))
                known = set(current)
                missing_bad = [url for url in BAD_TARGETS if url not in known]
                if len(missing_bad) > needed:
                    raise ValueError(f"{username}: monitor count changed; no changes committed.")
                candidates = missing_bad + [url for url in urls if url not in known and url not in BAD_TARGETS]
                selected = candidates[:needed]
                if len(selected) != needed:
                    raise ValueError(f"Not enough distinct URLs for {username}; no changes committed.")
                for url in selected:
                    name = f"Intentional HTTP {url.rsplit('/', 1)[-1]}" if url in BAD_TARGETS else f"{fake.company()} - {fake.word()}"[:100]
                    payload = MonitorCreate(
                        name=name, url=url, interval_seconds=args.interval,
                        failure_threshold=args.failure_threshold,
                    )
                    if not args.dry_run:
                        session.add(MonitorModel(owner_id=user_id, **payload.model_dump(mode="json")))
                plans.append((username, user_id, len(selected), len(current) + len(selected)))
        for username, user_id, added, total in plans:
            verb = "Would create" if args.dry_run else "Created"
            print(f"[{username}] {verb} {added} monitors; total {total}, including 3 failing URLs; owner_id={user_id}.")
        for url in BAD_TARGETS:
            print(f"[intentional failure] {url}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main(parse_args()))
    except (ValueError, httpx.HTTPError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
    except SQLAlchemyError as exc:
        print(f"[error] Database operation failed ({type(exc).__name__}). Check PostgreSQL and the project's database settings.", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
