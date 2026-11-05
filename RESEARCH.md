# Research

The documented concurrency policy allows one running job or workflow in a group. The default queue keeps one pending item and replaces that item on a later arrival. The expanded queue keeps up to 100 pending items and cannot be combined with cancellation of an active run. GitHub distinguishes the time a run starts waiting on the group from the time it was dispatched. This replay accepts the group event order as an explicit input. [GitHub Actions concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

A Windows runner issue reports that canceling a job while parallel steps were active could leave it stuck until forced termination. The report concerns runner execution. The replay models an immediate cancellation transition and makes no claim about how a runner stops. [Actions Runner issue 4830](https://github.com/actions/runner/issues/4830)

GitHub workflow run history and `gh run view` show what happened in existing runs. An offline replay serves a separate need during policy review by letting a team vary a small event sequence and inspect each resulting transition. [GitHub workflow run history](https://docs.github.com/en/actions/how-tos/monitor-workflows/view-workflow-run-history)

Workflow tools such as actionlint statically check workflow files. This project takes an already normalized policy and an ordered sequence of synthetic events, which makes the state transitions explicit during review. [actionlint project](https://github.com/rhysd/actionlint)
