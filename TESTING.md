# Testing

Run the suite from the project root with Python 3.11 or newer.

```sh
python -m unittest discover -s tests -v
```

The tests execute the CLI for pending replacement, immediate preemption, FIFO promotion, overflow, and rejection of an idle finish. They also cover strict JSON and size validation, private errors, and an OS pipe whose reader is already closed. A path test intercepts file access to verify that rejected spellings are blocked first.

```sh
python gha_concurrency_replay.py fixtures/single.json
python gha_concurrency_replay.py fixtures/preempt.json
python gha_concurrency_replay.py fixtures/max.json
python gha_concurrency_replay.py fixtures/idle-finish.json
```

The first three commands exit `0`. The final command exits `2` with an empty stdout stream. The tests and examples run locally without a GitHub token or a network connection.
