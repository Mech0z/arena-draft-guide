import urllib.error
import warnings
import csv
from pathlib import Path
from draftguide.ratings import Store, apply_picklist_csv


def test_picklist_sources_overlay_missing_scores_and_keep_comments(tmp_path):
    data = {
        "cards": [
            {"name": "Card One", "score": None, "rank": None, "rankOf": None, "ratings": []},
            {
                "name": "Card Two",
                "score": 55,
                "rank": 2,
                "rankOf": 3,
                "ratings": [{"source": "17Lands", "grade": None, "score": 95, "comment": "GIH WR 70%"}],
            },
        ]
    }
    path = tmp_path / "WOE.csv"
    path.write_text(
        "source,card_name,rating,rating_scale,comment,source_url\n"
        'Draftsim,"Card One",4.5,5,"Strong card, especially in Red",https://ratings.example/WOE\n'
        "Draftsim,Card Two,3.0,5,,https://ratings.example/WOE\n",
        encoding="utf-8",
    )

    result = apply_picklist_csv(data, path)
    first, second = result["cards"]
    assert first["score"] == 90
    assert first["averageRating"] == 4.5 and first["ratingSourceCount"] == 1
    assert first["rank"] == 1 and first["rankOf"] == 2
    assert first["ratings"][-1] == {
        "source": "Draftsim",
        "grade": "4.5/5",
        "score": 90,
        "comment": "Strong card, especially in Red",
        "sourceUrl": "https://ratings.example/WOE",
    }
    assert second["score"] == 60
    assert second["averageRating"] == 3.0
    assert second["rank"] == 2 and second["rankOf"] == 2
    assert second["ratings"][-1]["grade"] == "3/5"
    assert result["supplementalSources"] == [
        {"name": "Draftsim", "url": "https://ratings.example/WOE"}
    ]
    assert result["attribution"] == "https://ratings.example/WOE"


def test_picklist_csv_can_add_another_source_for_same_set(tmp_path):
    data = {"cards": [{"name": "Card One", "score": None, "ratings": []}]}
    path = tmp_path / "WOE.csv"
    path.write_text(
        "source,card_name,rating,rating_scale,comment,source_url\n"
        "Draftsim,Card One,4,5,,https://ratings.example/draftsim\n"
        "Community,Card One,3,5,Good late pick,https://ratings.example/community\n",
        encoding="utf-8",
    )
    result = apply_picklist_csv(data, path)
    card = result["cards"][0]
    assert card["score"] == 70
    assert card["averageRating"] == 3.5 and card["ratingSourceCount"] == 2
    assert [rating["source"] for rating in card["ratings"]] == ["Draftsim", "Community"]
    assert card["ratings"][1]["comment"] == "Good late pick"
    assert [source["name"] for source in result["supplementalSources"]] == ["Draftsim", "Community"]


def test_picklist_csv_ignores_unknown_or_invalid_rows(tmp_path):
    data = {"cards": [{"name": "Card One", "score": None, "ratings": []}]}
    path = tmp_path / "WOE.csv"
    path.write_text(
        "source,card_name,rating,rating_scale,comment,source_url\n"
        "Draftsim,Unknown,4,5,,\n"
        "Draftsim,Card One,9,5,,\n",
        encoding="utf-8",
    )
    assert apply_picklist_csv(data, path)["cards"][0]["score"] is None
    assert apply_picklist_csv({"cards": []}, tmp_path / "missing.csv") == {"cards": []}


def test_store_uses_local_picklist_when_public_source_is_unavailable(tmp_path, monkeypatch):
    picklists = tmp_path / "picklists"
    picklists.mkdir()
    (picklists / "WOE.csv").write_text(
        "source,card_name,rating,rating_scale,comment,source_url\n"
        "Draftsim,Card One,4,5,,https://ratings.example/WOE\n",
        encoding="utf-8",
    )
    store = Store(tmp_path)
    monkeypatch.setattr(store, "_get_public", lambda code, fmt: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    with warnings.catch_warnings(record=True) as seen:
        data = store.get("WOE")
    assert data["cards"][0]["score"] == 80
    assert data["cards"][0]["averageRating"] == 4.0
    assert data["attribution"] == "https://ratings.example/WOE"
    assert seen and "using local picklist CSV" in str(seen[0].message)


def test_saved_draftsim_picklists_have_expected_card_counts():
    root = Path(__file__).resolve().parents[1] / "data" / "picklists"
    for code, expected in (("WOE", 324), ("FRA", 295)):
        with (root / f"{code}.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == expected
        assert all(row["source"] == "Draftsim" and row["rating_scale"] == "5" for row in rows)
        assert all(row["source_url"].startswith("https://draftsim.com/") for row in rows)
        assert all("comment" in row for row in rows)
