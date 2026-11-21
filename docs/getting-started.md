---
layout: default
title: Getting started
---

# Getting started

This walks through a new two-package repo from scratch: write the code,
declare the targets, run the tests, and watch lirk skip everything that
didn't change. It takes about five minutes. If you already have a repo,
skip to [Existing repos](adopting.html), where `lirk init` writes the
BUILD files for you.

## Install

lirk needs Python 3.11 or newer, and nothing else.

```sh
pip install lirk
lirk --version
```

## 1. Mark the repo root

From an empty directory:

```sh
touch .lirk-root
```

Labels like `//app:app` are resolved from the repo root, and lirk finds
the root by looking for this file in the current directory and its
parents. It can stay empty.

## 2. Write some code

```
.lirk-root
greeting/
    greet.py
    test_greet.py
app/
    cli.py
    test_cli.py
```

`greeting/greet.py`:

```python
def greet(name):
    return f"Hello, {name}!"
```

`greeting/test_greet.py`:

```python
import unittest

from greeting.greet import greet


class GreetTest(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet("world"), "Hello, world!")
```

`app/cli.py` uses the other package:

```python
from greeting.greet import greet


def banner(name):
    return greet(name).upper()
```

`app/test_cli.py`:

```python
import unittest

from app.cli import banner


class BannerTest(unittest.TestCase):
    def test_banner(self):
        self.assertEqual(banner("world"), "HELLO, WORLD!")
```

These are ordinary `unittest` tests. pytest works just as well; see
[Using pytest](adopting.html#using-pytest).

## 3. Declare the targets

Each package directory gets a `BUILD.lirk` listing its targets.
`greeting/BUILD.lirk`:

```toml
[[target]]
name = "greeting"
type = "library"
srcs = ["greet.py"]

[[target]]
name = "greeting_test"
type = "test"
srcs = ["test_greet.py"]
deps = [":greeting"]
```

`app/BUILD.lirk`:

```toml
[[target]]
name = "app"
type = "library"
srcs = ["cli.py"]
deps = ["//greeting:greeting"]

[[target]]
name = "app_test"
type = "test"
srcs = ["test_cli.py"]
deps = [":app"]
```

A `library` is code other targets can depend on, and a `test` is code
lirk runs. `deps` names what a target uses: `:greeting` for a target in
the same package, `//greeting:greeting` for one in another package.

> You don't have to write the `deps` lines yourself. Leave them out,
> run `lirk fix`, and lirk adds them from your imports.

## 4. Run the tests

```
$ lirk test //...
  built  //greeting:greeting
  built  //app:app
  PASS   //app:app_test (0.1s)
  PASS   //greeting:greeting_test (0.1s)
lirk: 2/2 tests passed
lirk: OK
```

`//...` means every target in the repo. lirk checks each library
first (its files exist, it parses, and its imports match its `deps`),
then runs the tests.

Run it again:

```
$ lirk test //...
  cached  //greeting:greeting
  cached  //app:app
  cached  //app:app_test
  cached  //greeting:greeting_test
lirk: 2/2 tests passed
lirk: OK
```

Nothing changed, so nothing ran.

## 5. Change something

Edit `greeting/greet.py`, for example by adding a function, and run
again:

```
$ lirk test //...
  built  //greeting:greeting
  built  //app:app
  PASS   //app:app_test (0.1s)
  PASS   //greeting:greeting_test (0.1s)
lirk: 2/2 tests passed
lirk: OK
```

Both tests ran. `app` didn't change, but it depends on `greeting`, so
its result can no longer be trusted. Now edit only `app/cli.py`: this
time `greeting`'s test stays `cached`, because nothing it depends on
changed.

lirk compares file contents, not timestamps. Touching a file, switching
branches and back, or making a fresh clone doesn't cause reruns. Undo an
edit and you're back to the cached result.

## 6. Ignore lirk's cache in git

Add to `.gitignore`:

```
.lirk-cache.json
.lirk-cache.json.*.tmp
__pycache__/
*.pyc
```

`.lirk-cache.json` is lirk's record of what passed. It's local to your
machine, so don't commit it.

## What next

- **Run part of the repo:** `lirk test //app/...` (a package and
  everything under it), or `lirk test //app:app_test` (one target).
  [Commands](commands.html) has every form.
- **Read fixture files in a test?** Declare them as `data`, or edits to
  them won't trigger reruns. See [BUILD files](build-format.html).
- **Converting a real repo?** Read [Existing repos](adopting.html).
- **Curious why you can trust `cached`?** Read
  [How it works](how-it-works.html).
