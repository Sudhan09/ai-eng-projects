"""python -m demo: imported only when something asks for it (not up front)."""

from demo import core


def main():
    return core.make("main")


if __name__ == "__main__":
    main()
