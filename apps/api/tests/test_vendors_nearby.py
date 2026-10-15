from fastapi.testclient import TestClient


def test_nearby_requires_a_location(client: TestClient) -> None:
    assert client.get("/vendors/nearby").status_code == 422


def test_nearby_rejects_out_of_range_coordinates(client: TestClient) -> None:
    assert client.get("/vendors/nearby?lat=95&lng=103.68").status_code == 422
    assert client.get("/vendors/nearby?lat=1.34&lng=181").status_code == 422


def test_nearby_rejects_distances_over_the_limit(client: TestClient) -> None:
    response = client.get("/vendors/nearby?lat=1.34&lng=103.68&max_distance_m=99999")
    assert response.status_code == 422