"""填稿后的等待逻辑：交互终端按回车，非交互环境按秒数保留窗口。

这个测试存在的理由：以前无条件 input()，从 API 调用时 stdin 是 EOF，
浏览器会被立刻关掉，填好的稿子全丢。L2 交回里把这条列为头号风险。
"""

from pipeline.content.headline import _wait_mode


class FakeStdin:
    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_explicit_hold_wins():
    assert _wait_mode(30, FakeStdin(tty=True)) == ("sleep", 30)
    assert _wait_mode(30, FakeStdin(tty=False)) == ("sleep", 30)


def test_tty_waits_for_enter():
    assert _wait_mode(0, FakeStdin(tty=True)) == ("input", 0)


def test_non_tty_keeps_window_open():
    mode, seconds = _wait_mode(0, FakeStdin(tty=False))
    assert mode == "sleep"
    assert seconds >= 300  # 至少 5 分钟，够人过去点发布


def test_missing_stdin_is_treated_as_non_tty():
    mode, seconds = _wait_mode(0, None)
    assert mode == "sleep"
    assert seconds >= 300
