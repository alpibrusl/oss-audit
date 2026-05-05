# Proposed lex stdlib roadmap — 10 modules to maximize coverage

A pragmatic next-quarter list, picked by **what's missing today vs. what
real production code uses every day**, not by feature parity with any
specific incumbent. Each entry has a 1-line role, why the absence
costs every program something, the public API, a minimal example, and
notes on which Rust crate to wrap.

The 10, ordered by leverage (highest leverage first):

| # | Module | One-line role |
|---|--------|---------------|
| 1 | [`std.collections`](#1-stdcollections) | Hash map, set, deque — the missing container shapes |
| 2 | [`std.regex`](#2-stdregex) | The universal text primitive |
| 3 | [`std.fs`](#3-stdfs) | Walk, glob, stat — the missing filesystem |
| 4 | [`std.sql`](#4-stdsql) | SQLite as the default embedded DB |
| 5 | [`std.http`](#5-stdhttp) | Rich HTTP client (auth, retry, streaming) |
| 6 | [`std.datetime`](#6-stddatetime) | Parse, format, arithmetic across timezones |
| 7 | [`std.crypto`](#7-stdcrypto) | Hash / HMAC / base64 / hex / secure random |
| 8 | [`std.config`](#8-stdconfig) | TOML, YAML, CSV, dotenv |
| 9 | [`std.test`](#9-stdtest) | First-class user-facing test framework |
| 10 | [`std.log`](#10-stdlog) | Structured logging with `[log]` effect |

The argument for the ordering: items 1–3 are foundational data types and
text/file primitives — every non-toy program needs them. 4–6 are
"production starts here" — DB, HTTP, dates. 7–8 are security + config
table-stakes. 9–10 are quality-of-life that pay back over the project's
lifetime.

---

## 1. `std.collections`

**Why the absence hurts every program.** Lex has `List[T]` but no
`Map[K, V]`, `Set[T]`, or `Deque[T]`. The Rubric POC ended up doing
verdict-table dispatch via nested `match` because there's no way to do
"given a verdict code, look up its action set". Without a hash map,
every dynamic-key lookup degrades to either an O(n) list scan or a giant
`match` expression. This is the highest-leverage module on the list.

**API:**

```lex
# Map[K, V] — persistent hash map (immutable; ops return new map)
fn map.new() -> Map[K, V]
fn map.get(m :: Map[K, V], k :: K) -> Option[V]
fn map.insert(m :: Map[K, V], k :: K, v :: V) -> Map[K, V]
fn map.remove(m :: Map[K, V], k :: K) -> Map[K, V]
fn map.contains(m :: Map[K, V], k :: K) -> Bool
fn map.len(m :: Map[K, V]) -> Int
fn map.keys(m :: Map[K, V]) -> List[K]
fn map.values(m :: Map[K, V]) -> List[V]
fn map.entries(m :: Map[K, V]) -> List[(K, V)]
fn map.merge(a :: Map[K, V], b :: Map[K, V]) -> Map[K, V]   # b overrides a

# Set[T] — persistent hash set
fn set.new() -> Set[T]
fn set.contains(s :: Set[T], x :: T) -> Bool
fn set.insert(s :: Set[T], x :: T) -> Set[T]
fn set.remove(s :: Set[T], x :: T) -> Set[T]
fn set.union(a :: Set[T], b :: Set[T]) -> Set[T]
fn set.intersect(a :: Set[T], b :: Set[T]) -> Set[T]
fn set.diff(a :: Set[T], b :: Set[T]) -> Set[T]
fn set.to_list(s :: Set[T]) -> List[T]

# Deque[T] — double-ended queue
fn deque.new() -> Deque[T]
fn deque.push_back(q :: Deque[T], x :: T) -> Deque[T]
fn deque.push_front(q :: Deque[T], x :: T) -> Deque[T]
fn deque.pop_back(q :: Deque[T]) -> Option[(T, Deque[T])]
fn deque.pop_front(q :: Deque[T]) -> Option[(T, Deque[T])]
fn deque.len(q :: Deque[T]) -> Int
```

**Example — actions table for the POC's verdict layer:**

```lex
let actions := map.new()
  |> map.insert("bet-on-it",  "Adopt or invest")
  |> map.insert("worth-helping", "Fork or fund")
  |> map.insert("indeterminate", "Re-audit with all pillars")

match map.get(actions, verdict.code) {
  Some(a) => a,
  None    => "no action",
}
```

**Implementation.** Wrap `im::HashMap` / `im::HashSet` (persistent,
structural sharing — fits lex's immutability-by-default story) and
`std::collections::VecDeque` for `Deque`. ~2 weeks of work each.

---

## 2. `std.regex`

**Why the absence hurts every program.** `str.split` / `str.contains`
get you ~30% of text-processing needs. Anything beyond — extracting
groups, validating format, replacing patterns — currently requires
hand-rolling a state machine. Every parser, every scraper, every config
validator wants `regex.find_all(rx, s)`.

**API:**

```lex
type Regex      # opaque, compiled
type Match = { text :: Str, start :: Int, end :: Int, groups :: List[Str] }

fn regex.compile(pattern :: Str) -> Result[Regex, Str]
fn regex.is_match(r :: Regex, s :: Str) -> Bool
fn regex.find(r :: Regex, s :: Str) -> Option[Match]
fn regex.find_all(r :: Regex, s :: Str) -> List[Match]
fn regex.replace(r :: Regex, s :: Str, replacement :: Str) -> Str
fn regex.replace_all(r :: Regex, s :: Str, replacement :: Str) -> Str
fn regex.split(r :: Regex, s :: Str) -> List[Str]
```

**Example — extract GitHub URLs from text (HN suggester pattern):**

```lex
let url_re := match regex.compile("https?://(?:www\\.)?github\\.com/[\\w./-]+") {
  Ok(r)  => r,
  Err(_) => panic,
}
let matches := regex.find_all(url_re, post_text)
list.map(matches, fn (m :: Match) -> Str { m.text })
```

**Implementation.** Wrap the Rust `regex` crate. Pure — no effect.
~1 week.

---

## 3. `std.fs`

**Why the absence hurts every program.** `io.read` / `io.write` handle
single files but you can't list a directory, walk a tree, or glob.
Every CLI tool, every build system, every audit / scanner needs at
minimum `fs.walk("./src")`. The Rubric POC's ingestion layer is
50% directory walking.

**API:**

```lex
type FileStat = { size :: Int, mtime :: Int, is_dir :: Bool, is_file :: Bool }
type FsError  = NotFound | PermissionDenied | AlreadyExists | Other(Str)

fn fs.exists(path :: Str)        -> [fs] Bool
fn fs.is_file(path :: Str)       -> [fs] Bool
fn fs.is_dir(path :: Str)        -> [fs] Bool
fn fs.list_dir(path :: Str)      -> [fs] Result[List[Str], FsError]
fn fs.walk(path :: Str)          -> [fs] Result[List[Str], FsError]   # recursive
fn fs.glob(pattern :: Str)       -> [fs] Result[List[Str], FsError]
fn fs.mkdir(path :: Str)         -> [fs] Result[Nil, FsError]
fn fs.mkdir_p(path :: Str)       -> [fs] Result[Nil, FsError]
fn fs.remove(path :: Str)        -> [fs] Result[Nil, FsError]
fn fs.remove_dir(path :: Str, recursive :: Bool) -> [fs] Result[Nil, FsError]
fn fs.copy(src :: Str, dst :: Str) -> [fs] Result[Nil, FsError]
fn fs.move(src :: Str, dst :: Str) -> [fs] Result[Nil, FsError]
fn fs.stat(path :: Str)          -> [fs] Result[FileStat, FsError]
```

**Effect note.** Splitting `[fs]` out from `[io]` would let `lex audit
--effect fs` flag exactly the functions that touch the filesystem
(separately from network or stdout). Lex's effect-as-types pitch is
strongest when the effects are fine-grained.

**Example — count lines of Python code in a tree:**

```lex
fn loc(root :: Str) -> [fs] Int {
  match fs.walk(root) {
    Ok(paths) => list.fold(paths, 0, fn (acc :: Int, p :: Str) -> Int {
      if str.ends_with(p, ".py") {
        match io.read(p) {
          Ok(content) => acc + list.len(str.split(content, "\n")),
          Err(_)      => acc,
        }
      } else { acc }
    }),
    Err(_) => 0,
  }
}
```

**Implementation.** Rust's `std::fs` + `walkdir` + `globwalk` crates.
~2 weeks.

---

## 4. `std.sql`

**Why the absence hurts every program.** SQLite is the default embedded
DB for ~every CLI app, ~every desktop app, ~every "small service" in
the world. Rubric uses it for the audit history. Without `std.sql`,
any stateful lex program either reinvents storage or shells out.

**API:**

```lex
type Db        # opaque connection, [sql] capability bound
type Value = SqlNull | SqlInt(Int) | SqlFloat(Float) | SqlStr(Str) | SqlBytes(Bytes)
type Row   = Map[Str, Value]   # column name -> value

fn sql.open(path :: Str) -> [sql, fs] Result[Db, Str]
fn sql.exec(db :: Db, query :: Str, params :: List[Value]) -> [sql] Result[Int, Str]
fn sql.query(db :: Db, query :: Str, params :: List[Value]) -> [sql] Result[List[Row], Str]
fn sql.transaction(db :: Db, body :: fn(Db) -> [sql] Result[T, Str]) -> [sql] Result[T, Str]
fn sql.close(db :: Db) -> [sql] Nil
```

**Effect note.** A separate `[sql]` effect is overkill for v1; bundling
under `[fs]` (since SQLite is a file) is fine.

**Example:**

```lex
fn save_audit(db :: Db, repo :: Str, score :: Float) -> [sql] Result[Int, Str] {
  sql.exec(db, "INSERT INTO audits (repo, score) VALUES (?, ?)",
    [SqlStr(repo), SqlFloat(score)])
}
```

**Implementation.** Wrap `rusqlite`. Define a `Driver` trait so
Postgres/MySQL can plug in later via `sql.open_postgres(uri)` etc. ~3-4
weeks for SQLite alone.

---

## 5. `std.http`

**Why `net.get` / `net.post` aren't enough.** Real HTTP needs auth
(Bearer, Basic, mTLS), retries with backoff, streaming responses,
multipart upload, custom headers, query-string building, redirect
control, timeouts, and structured error handling. `net.*` is the kernel
syscall; `http.*` is the production client.

**API:**

```lex
type Request  = {
  method      :: Str,
  url         :: Str,
  headers     :: Map[Str, Str],
  body        :: Option[Bytes],
  timeout_ms  :: Option[Int],
}

type Response = {
  status   :: Int,
  headers  :: Map[Str, Str],
  body     :: Bytes,
}

type HttpError = NetworkError(Str) | TimeoutError | TlsError(Str) | DecodeError(Str)

fn http.send(req :: Request) -> [net] Result[Response, HttpError]
fn http.get(url :: Str)       -> [net] Result[Response, HttpError]
fn http.post(url :: Str, body :: Bytes, content_type :: Str) -> [net] Result[Response, HttpError]

# Builder helpers (pure — return a new Request)
fn http.with_header(req :: Request, k :: Str, v :: Str) -> Request
fn http.with_auth(req :: Request, scheme :: Str, token :: Str) -> Request
fn http.with_query(req :: Request, params :: Map[Str, Str]) -> Request
fn http.with_timeout_ms(req :: Request, ms :: Int) -> Request
fn http.with_retry(req :: Request, max_attempts :: Int, backoff_ms :: Int) -> Request

# Decoders
fn http.json_body(r :: Response) -> Result[Json, HttpError]
fn http.text_body(r :: Response) -> Result[Str, HttpError]
```

**Example — GitHub API call with auth:**

```lex
let req := http.get("https://api.github.com/repos/alpibrusl/oss-audit")
  |> http.with_auth("Bearer", env_token)
  |> http.with_header("Accept", "application/vnd.github+json")
  |> http.with_retry(3, 200)

match http.send(req) {
  Ok(r)  => http.json_body(r),
  Err(e) => Err(NetworkError(...)),
}
```

**Implementation.** Wrap `ureq` (already a lex dep) or `reqwest`.
~3 weeks.

---

## 6. `std.datetime`

**Why `time.now` isn't enough.** Real time work is parsing ISO 8601 from
APIs, formatting "X days ago" for users, computing "next Tuesday at 9am
in the user's timezone", and handling daylight saving correctly. Lex
has the tick; it doesn't have the calendar.

**API:**

```lex
type Instant      # opaque, monotonic UTC nanoseconds
type Duration     # opaque, signed nanoseconds
type DateTime = {
  year :: Int, month :: Int, day :: Int,
  hour :: Int, minute :: Int, second :: Int, nano :: Int,
  tz   :: Tz,
}
type Tz = Utc | Local | Offset(Int)   # offset minutes from UTC

fn datetime.now() -> [time] Instant
fn datetime.parse_iso(s :: Str) -> Result[Instant, Str]
fn datetime.format_iso(t :: Instant) -> Str
fn datetime.parse_rfc3339(s :: Str) -> Result[Instant, Str]
fn datetime.format(t :: Instant, format :: Str) -> Str
fn datetime.parse(s :: Str, format :: Str) -> Result[Instant, Str]
fn datetime.to_components(t :: Instant, tz :: Tz) -> DateTime
fn datetime.from_components(dt :: DateTime) -> Result[Instant, Str]
fn datetime.add(t :: Instant, d :: Duration) -> Instant
fn datetime.diff(a :: Instant, b :: Instant) -> Duration
fn datetime.duration_seconds(s :: Float) -> Duration
fn datetime.duration_minutes(m :: Int) -> Duration
fn datetime.duration_days(d :: Int) -> Duration
```

**Implementation.** Wrap `chrono` + `chrono-tz`. ~2 weeks.

---

## 7. `std.crypto`

**Why the absence hurts every program.** Without hashing you can't
implement caches, ETags, checksums, content-addressed storage. Without
HMAC you can't sign requests. Without base64/hex you can't encode
binary for transport. Without secure random you can't generate tokens
or session IDs. This is the smallest module in the list and the
hardest to live without.

**API:**

```lex
fn crypto.sha256(data :: Bytes) -> Bytes
fn crypto.sha512(data :: Bytes) -> Bytes
fn crypto.md5(data :: Bytes) -> Bytes               # for legacy compatibility only
fn crypto.hmac_sha256(key :: Bytes, data :: Bytes) -> Bytes
fn crypto.base64_encode(data :: Bytes) -> Str
fn crypto.base64_decode(s :: Str) -> Result[Bytes, Str]
fn crypto.hex_encode(data :: Bytes) -> Str
fn crypto.hex_decode(s :: Str) -> Result[Bytes, Str]
fn crypto.constant_time_eq(a :: Bytes, b :: Bytes) -> Bool
fn crypto.random(n :: Int) -> [random] Bytes        # cryptographically secure
```

**Effect note.** `[random]` is a new fine-grained effect distinct from
`[io]` — it's the syscall to the OS RNG. Worth surfacing because
"this function generates randomness" is a security-relevant property
the type system can flag (e.g. `lex audit --effect random` to find every
token-generating function).

**Implementation.** `sha2`, `hmac`, `base64`, `hex`, `rand` crates. ~1
week — these are all small wrappers.

---

## 8. `std.config`

**Why bundle these together.** TOML, YAML, CSV, and `.env` are how
config and tabular data move into and out of programs. Each is a
~few-hundred-line wrapper around an existing Rust crate; bundling them
reduces the per-module overhead and lets them share a `Json` AST with
`std.json`.

**API:**

```lex
# Reuse the Json AST from std.json as the parsed representation
fn toml.parse(s :: Str)        -> Result[Json, Str]
fn toml.stringify(v :: Json)   -> Str

fn yaml.parse(s :: Str)        -> Result[Json, Str]
fn yaml.stringify(v :: Json)   -> Str

fn dotenv.parse(s :: Str)      -> Result[Map[Str, Str], Str]

# CSV is structurally different; it gets its own type
type Csv = { headers :: List[Str], rows :: List[List[Str]] }
fn csv.parse(s :: Str, has_header :: Bool) -> Result[Csv, Str]
fn csv.stringify(c :: Csv) -> Str
```

**Example — read pyproject.toml, extract dependencies:**

```lex
fn deps(repo_root :: Str) -> [fs] Result[List[Str], Str] {
  let body := io.read(str.concat(repo_root, "/pyproject.toml")) |> result.expect
  let tree := toml.parse(body) |> result.expect
  # [project] dependencies = [...]
  ...
}
```

**Implementation.** `toml`, `serde_yaml`, `csv`, `dotenvy` crates. ~2
weeks total.

---

## 9. `std.test`

**Why a userland test framework matters.** Lex has fuzzing
infrastructure under the hood (`crates/conformance/`, `tests/fuzz/`),
but no userland surface for "I want to write `test_my_function` and
have lex run them all". Every language community I've seen lives or
dies by its testing story — pytest for Python, cargo test for Rust,
Jest for JS. Without one, "TDD in lex" is hand-rolled.

**API:**

```lex
type TestResult = Pass | Fail(Str) | Skip(Str)
type Test  = { name :: Str, body :: fn() -> TestResult }
type Suite = { name :: Str, tests :: List[Test] }

# Assertions
fn test.assert(cond :: Bool, msg :: Str)         -> TestResult
fn test.assert_eq(a :: T, b :: T)                -> TestResult
fn test.assert_neq(a :: T, b :: T)               -> TestResult
fn test.assert_close(a :: Float, b :: Float, eps :: Float) -> TestResult

# Runner
fn test.run_suite(s :: Suite) -> [io] Bool   # true if all passed

# Property-based
type Generator[T]
fn gen.int(min :: Int, max :: Int)                  -> Generator[Int]
fn gen.float(min :: Float, max :: Float)            -> Generator[Float]
fn gen.str(min_len :: Int, max_len :: Int)          -> Generator[Str]
fn gen.list(elem :: Generator[T], min :: Int, max :: Int) -> Generator[List[T]]
fn gen.choice(options :: List[T])                   -> Generator[T]
fn test.property(name :: Str, gen :: Generator[T], body :: fn(T) -> Bool) -> Test
```

**Example — port the Rubric sanity matrix:**

```lex
fn rubric_suite() -> Suite {
  {
    name: "rubric agreement",
    tests: [
      { name: "polars-style", body: fn() -> TestResult {
        let r := make_report(90.0, Available, 0.0, Skipped, 0.0, Skipped)
        let v := compute_verdict(r)
        test.assert_eq(v.code, "indeterminate")
      }},
      ...
    ],
  }
}
```

**Implementation.** Lex already has the conformance harness; this
exposes the same machinery as a userland API. ~2 weeks.

---

## 10. `std.log`

**Why structured logging belongs in stdlib.** Once a program is bigger
than a script, `io.print` becomes painful (no levels, no fields,
goes to stdout instead of a sink). Every production program ends up
re-implementing this. Baking it in fixes the format across the
ecosystem and gives the lex effect system another fine-grained channel
to track.

**API:**

```lex
type Level = Debug | Info | Warn | Error
type LogFormat = Text | Json

fn log.debug(msg :: Str) -> [log] Nil
fn log.info(msg :: Str)  -> [log] Nil
fn log.warn(msg :: Str)  -> [log] Nil
fn log.error(msg :: Str) -> [log] Nil

# Structured field attachment (returns a context handle)
fn log.with(fields :: Map[Str, Str], body :: fn() -> [log] T) -> [log] T

# Configuration
fn log.set_level(l :: Level)        -> [io] Nil   # configures the global sink
fn log.set_format(f :: LogFormat)   -> [io] Nil
fn log.set_sink(path :: Str)        -> [io, fs] Nil   # file or `-` for stderr
```

**Effect note.** `[log]` is distinct from `[io]` because: (a) logs go to
a runtime-configured sink, not directly to stdout/stderr; (b) lex
programs can declare "I emit logs but I don't do other I/O", which is a
useful guarantee for libraries; (c) `lex audit --effect log` shows
exactly the call sites that emit logs — handy for compliance.

**Example:**

```lex
fn handle_request(req :: Request) -> [net, log] Response {
  log.with({"method": req.method, "path": req.path}, fn() -> [net, log] Response {
    log.info("request received")
    let resp := route(req)
    log.with({"status": int.to_str(resp.status)}, fn() -> [log] Nil {
      log.info("request completed")
    })
    resp
  })
}
```

**Implementation.** Hand-rolled is fine; or wrap `tracing` if going
deeper. ~1-2 weeks for a clean v1.

---

## Total effort estimate

If a focused team picks this up, the rough costs:

| Module | Estimate |
|--------|----------|
| `std.collections` | 2 weeks |
| `std.regex`       | 1 week  |
| `std.fs`          | 2 weeks |
| `std.sql`         | 3-4 weeks |
| `std.http`        | 3 weeks |
| `std.datetime`    | 2 weeks |
| `std.crypto`      | 1 week  |
| `std.config`      | 2 weeks |
| `std.test`        | 2 weeks |
| `std.log`         | 1-2 weeks |
| **Total**         | **~5 months single-developer; ~3 months two-developer** |

That's "one focused quarter" to land all 10. After this, lex covers
~90% of what production CLIs, daemons, scrapers, audit tools, agent
sandboxes, and small services need — without specialty modules
(numpy-equivalent, ML, cloud SDKs) which are a separate, larger
project.

## What's deliberately not on this list

Ten modules I considered and dropped for v1:

- **`std.async`** — concurrency primitives. Lex's effect system has
  natural async semantics already; `[net]` calls are I/O-bound and the
  runtime can multiplex. Worth a separate design pass before stdlib.
- **`std.cli`** — argparse. The lex toolchain ships ACLI; user
  programs probably want a thin wrapper but it's a v1.5 module.
- **`std.process`** (rich subprocess) — `proc.spawn` works for the
  basic case. Streaming stdin/stdout is a v2 feature.
- **`std.html`** — HTML parsing. Specialty (only scrapers use it).
- **`std.compression`** — gzip/zip/tar. Specialty.
- **`std.image`**, **`std.pdf`**, **`std.numpy`** — domain-specific.
- **`std.cloud`** — AWS/GCP/Azure SDKs. Massive surface, niche per
  customer; better as third-party.
- **`std.git`** — git operations. Useful but `proc.spawn("git", ...)`
  works fine until you need libgit2 perf.

These are all valid stdlib citizens **eventually**; they just don't
belong in the first 10 because they cost as much as a top-10 module
each but cover narrower use cases.
