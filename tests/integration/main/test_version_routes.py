"""
Test routes for routes for getting version
"""


# pylint: disable=redefined-outer-name,unused-argument

def test_version_route_successful(client):
    """
    Test version route when successful
    """
    response = client.get("/version", follow_redirects=True)
    assert response.status_code == 200
    assert b"You are currently using version" in response.data
