from aiofetch.transport import HttpTransport, Response


class Silent:
    """Two methods with the right shapes, and no aiofetch base class at all."""

    async def get(self, path, params=None):
        return Response(204)

    async def aclose(self):
        pass


def test_a_response_decodes_its_body_as_json():
    response = Response(200, b'{"id": "7", "name": "item 7"}')
    assert response.json() == {"id": "7", "name": "item 7"}
    assert response.headers == {}


def test_anything_with_get_and_aclose_is_a_transport():
    assert isinstance(Silent(), HttpTransport)
    assert not isinstance(object(), HttpTransport)
