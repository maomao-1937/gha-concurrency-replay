# gha-concurrency-replay

[![tests](https://github.com/maomao-1937/gha-concurrency-replay/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/gha-concurrency-replay/actions/workflows/tests.yml)

Replay a local event trace to see which GitHub Actions runs start, wait, get replaced, or get canceled within one concurrency group. Python 3.11 or newer is sufficient.

```sh
python gha_concurrency_replay.py fixtures/single.json
```

```json
{"queue":"single","cancel_in_progress":false,"events":["arrive","arrive","arrive","finish"]}
```

```json
{"events":[{"id":1,"action":"started"},{"id":2,"action":"queued"},{"id":3,"action":"replaced","replaced_id":2},{"id":1,"action":"finished","promoted_id":3}],"running":3,"pending":[]}
```

Use exactly the three input fields shown above. The input order is the order events are presented to the already normalized group. Each arrival gets a numeric ID starting at 1. Each finish uses the running ID and promotes the next pending run if available. A finish while idle invalidates the entire trace.

| Configuration | Arrival while a run is active |
| --- | --- |
| `single` with `false` | Queues one pending arrival and replaces any previous pending arrival |
| `single` with `true` | Cancels the running arrival and immediately starts the new one |
| `max` with `false` | Queues up to 100 pending arrivals in FIFO order and rejects overflow |

`max` with `true` is invalid. The output uses fixed action names and synthetic IDs. The optional `replaced_id`, `cancelled_id`, and `promoted_id` identify the other run affected by a transition. An idle group has `null` in `running`.

Exit `0` means the trace was valid, including when an arrival was rejected because the queue was full. Exit `2` means invalid arguments or input, or an I/O failure. Input errors produce a fixed diagnostic on stderr and no result on stdout.

Provide a regular UTF-8 JSON file up to 1 MiB. The CLI rejects duplicate keys, nonfinite values, and lone surrogate code points. It checks path spellings before filesystem access and accepts native absolute drive paths on Windows. Direct URIs, UNC paths, and Windows device spellings are refused. Choose a trusted path and directory. Filesystem resolution can follow symlinks, junctions, and mounts, including mapped drives. The CLI does not verify where those resolve.

The model treats cancellation as an immediate state transition. Workflow expression evaluation, dispatch ordering, runner signals, and live timing are outside its scope. See [research notes](RESEARCH.md) and [test coverage](TESTING.md).

## 中文

用本地事件表回放一个已归一化的 GitHub Actions 并发组，查看哪些运行启动、等待、被替换或被取消。使用 Python 3.11 或更新版本运行上面的命令即可。

输入必须包含示例中的三个字段。按事件给定顺序执行，每个 `arrive` 从 1 开始分配编号。`finish` 结束当前运行，有等待项时立即补位。空闲时收到 `finish` 会使整条轨迹无效。

- `single` 加 `false` 只保留一个等待项。后到的运行替换已有等待项。
- `single` 加 `true` 取消当前运行，并立即启动新运行。
- `max` 加 `false` 按先进先出顺序最多保留 100 个等待项，队列满时拒绝新到的运行。`max` 加 `true` 无效。

输出包含每条事件对应的编号和动作，以及最终运行编号与等待队列。若当前空闲，`running` 为 `null`。有效轨迹退出码为 `0`，即使队列满时有运行被拒绝。参数、输入或 I/O 失败时退出码为 `2`。

输入限 1 MiB 的普通 UTF-8 JSON 文件。请使用可信路径和目录。路径的字面检查会拒绝 URI、UNC 路径和 Windows 设备路径，但符号链接、目录联接、挂载点或映射驱动器仍由操作系统解析。回放仅描述组内状态变化。表达式求值、工作流触发顺序、运行器信号和实际时延超出模型范围。
