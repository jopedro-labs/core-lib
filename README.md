# core-lib

![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-0.1.0-58a6ff?style=flat-square)
![CI](https://github.com/jopedro-labs/core-lib/actions/workflows/ci.yml/badge.svg?branch=main)
<br />
![Linter](https://img.shields.io/badge/linter-Ruff-000000?style=flat-square&logo=python&logoColor=white)
![Type Check](https://img.shields.io/badge/types-mypy%20strict-2A6DB2?style=flat-square&logo=python&logoColor=white)
![GNU Make](https://img.shields.io/badge/env-GNU%20Make-active?style=flat-square&logo=gnu-make&logoColor=white)
![MIT License](https://img.shields.io/badge/license-MIT-607D8B?style=flat-square)

Shared Python support library. Provides common utilities (logging, file I/O) for internal projects.

---

## Installation

Add to your project's `requirements.txt` or `pyproject.toml`:

```txt
# requirements.txt
core-lib @ git+https://github.com/jopedro-labs/core-lib.git
```

```toml
# pyproject.toml
dependencies = [
    "core-lib @ git+https://github.com/jopedro-labs/core-lib.git",
]
```

Pin to a specific version:

```txt
core-lib @ git+https://github.com/jopedro-labs/core-lib.git@v0.1.0
```

---

## Modules

### `core_lib.logger`

ANSI-colored terminal logger. Outputs to stdout (or stderr for errors) with timestamps. No file persistence.

```python
from core_lib.logger import logger

logger.info("Starting job")
logger.success("Job completed")
logger.warning("Retrying...")
logger.error("Something failed", exception=ValueError("details"))
logger.section("Phase 1")       # bold header
logger.subsection("Step 1.1")   # bold subheader
logger.print("raw output")
```

You can also instantiate `Logger` directly if you need an isolated instance:

```python
from core_lib.logger import Logger

my_logger = Logger()
```

### `core_lib.file_utils`

Safe file reading utilities. Always returns a string — never raises.

```python
from core_lib.file_utils import load_file_content

content = load_file_content("/path/to/file.txt")  # "" if missing or unreadable
```

---

## Requirements

- Python >= 3.10
- No external dependencies

---

## Development

```bash
git clone https://github.com/jopedro-labs/core-lib.git
cd core-lib
make install
```

Run all checks (lint, types, tests): 

```bash
make check
```

Individual commands:

| Command       | Description                    |
|---------------|--------------------------------|
| `make lint`   | Lint with ruff                 |
| `make type`   | Type check with mypy           |
| `make test`   | Run tests with pytest          |
| `make check`  | Run all three in sequence      |

---

## License

Distributed under the MIT License.

Developed and maintained by **João Pedro** ([@JoPedro15](https://github.com/JoPedro15)).

> *Fueled by Espresso, CrossFit WODs, and powered by Gemini AI.* ☕🏋️‍♂️🤖