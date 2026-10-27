import importlib.resources


def test_the_package_ships_its_py_typed_marker():
    assert (importlib.resources.files("aiofetch") / "py.typed").is_file()
