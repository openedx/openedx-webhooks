"""
Test the Faker class and its helpers.
"""

import pytest
import requests
import requests_mock

from . import faker


# pylint: disable=missing-timeout

class MyException(faker.FakerException):
    status_code = 501


class MyFake(faker.Faker):
    """
    Our Faker-derived fake API for these tests.
    """
    def __init__(self, host):
        super().__init__(host)
        self.add_middleware(self.no_foo_middleware)

    def no_foo_middleware(self, request, context):
        """
        Middleware that fails a request if "foo" is in the query string.
        """
        if "foo" in request.query:
            context.status_code = 789
            return {}
        return None

    @faker.route(r"/api/something/(?P<id>.*)")
    def _get_something(self, match, _request, _context):
        return {"hello": "there", "id": match["id"]}

    @faker.route(r"/api/something/(?P<id>.*)", "POST")
    def _post_something(self, match, _request, _context):
        return {"created": match["id"]}

    @faker.route(r"/api/something/(?P<id>.*)", "DELETE")
    def _delete_something(self, _match, _request, context):
        context.status_code = 204

    @faker.route(r"/api/bad")
    def _get_bad(self, _match, _request, _context):
        raise MyException("Bad!")

    @faker.route(r"/api/status")
    def _get_status(self, _match, request, context):
        context.status_code = int(request.qs["code"][0])


@pytest.fixture
def my_fake():
    """
    A pytest fixture to create an instance of MyFake.
    """
    mocker = requests_mock.Mocker(real_http=False, case_sensitive=True)
    mocker.start()
    # Add another host so we can include tests that hit other sites.
    mocker.get("https://some.other.host/", text="")

    try:
        the_fake = MyFake(host="https://myapi.com")
        the_fake.install_mocks(mocker)
        yield the_fake
    finally:
        mocker.stop()


def test_json_data(my_fake):
    resp = requests.get("https://myapi.com/api/something/ME-123")
    assert resp.status_code == 200
    assert resp.json() == {"hello": "there", "id": "ME-123"}

def test_post(my_fake):
    resp = requests.post("https://myapi.com/api/something/ME-456")
    assert resp.status_code == 200
    assert resp.json() == {"created": "ME-456"}

def test_exception(my_fake):
    resp = requests.get("https://myapi.com/api/bad")
    assert resp.status_code == 501
    assert resp.json() == {"error": "Bad!"}

def test_query_and_status(my_fake):
    resp = requests.get("https://myapi.com/api/status?code=477")
    assert resp.status_code == 477
    assert resp.text == ""

def test_middleware(my_fake):
    """Middleware can interrupt handler execution."""
    resp = requests.get("https://myapi.com/api/status?code=477&foo")
    assert resp.status_code == 789


@pytest.mark.parametrize("method, url", [
    ("GET", "https://myapi.com/nothing"),
    ("GET", "https://myapi.com"),
    ("POST", "https://myapi.com/api/status"),
    ("GET", "http://myapi.com/api/something/ME-123"),
    ("GET", "https://otherapi.com/api/something/ME-123"),
])
def test_no_address(my_fake, method, url):
    with pytest.raises(requests_mock.NoMockAddress):
        requests.request(method, url)

def test_requests_made(my_fake):
    requests.get("https://myapi.com/api/something/1")
    requests.get("https://myapi.com/api/something/1234")
    requests.post("https://myapi.com/api/something/labels")
    requests.delete("https://myapi.com/api/something/bug123")
    requests.get("https://some.other.host/")
    assert my_fake.requests_made() == [
        ("/api/something/1", "GET"),
        ("/api/something/1234", "GET"),
        ("/api/something/labels", "POST"),
        ("/api/something/bug123", "DELETE"),
    ]
    assert my_fake.requests_made(method="GET") == [
        ("/api/something/1", "GET"),
        ("/api/something/1234", "GET"),
    ]
    assert my_fake.requests_made(r"123") == [
        ("/api/something/1234", "GET"),
        ("/api/something/bug123", "DELETE"),
    ]
    assert my_fake.requests_made(r"123", "GET") == [
        ("/api/something/1234", "GET"),
    ]

def test_reset_mock(my_fake):
    requests.get("https://myapi.com/api/something/1")
    requests.get("https://myapi.com/api/something/1234")
    my_fake.reset_mock()
    requests.post("https://myapi.com/api/something/labels")
    requests.delete("https://myapi.com/api/something/bug123")
    requests.get("https://some.other.host/")
    assert my_fake.requests_made() == [
        ("/api/something/labels", "POST"),
        ("/api/something/bug123", "DELETE"),
    ]

def test_readonly(my_fake):
    requests.get("https://myapi.com/api/something/1")
    requests.get("https://myapi.com/api/something/1234")
    requests.get("https://some.other.host/")
    my_fake.assert_readonly()

def test_not_readonly(my_fake):
    requests.get("https://myapi.com/api/something/1")
    requests.get("https://myapi.com/api/something/1234")
    requests.post("https://myapi.com/api/something/labels")
    requests.delete("https://myapi.com/api/something/bug123")
    requests.get("https://some.other.host/")
    with pytest.raises(AssertionError):
        my_fake.assert_readonly()
