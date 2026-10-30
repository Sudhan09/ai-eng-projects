"""A week whose own driver isn't written yet (a new week): every Part has "a function of yours", and its Try:
suggestions come from its tests. The week's own driver (drivers/w5.py) replaces this one once its code has an entry
point worth typing into, like an endpoint or a command."""

from _input import run_call

ANY_PART = True  # the server asks for each Part of the week by its label


class EveryPart(dict):
    def __missing__(self, part):
        self[part] = {"entries": {"call": {"label": "a function of yours", "hint": 'module.function("some text", 3)', "run": run_call}},
                      "scenarios": []}
        return self[part]


PARTS = EveryPart()
