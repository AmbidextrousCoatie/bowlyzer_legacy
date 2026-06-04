"""Club matrix resolves NFC/NFD club labels and returns matrix rows."""

from app import create_app


def test_get_club_matrix_resolves_nfd_club_param():
    app = create_app()
    client = app.test_client()
    club_nfd = "Adler Nu\u0308rnberg"
    r = client.get(
        "/league/get_club_matrix",
        query_string={"database": "db_real_merged", "club": club_nfd},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["selected_club"]
    assert len(data["matrix"]["rows"]) > 0
    assert data["matrix"]["club"] == data["selected_club"]
