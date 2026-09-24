"""Grouping maths, with made-up fingerprints. No photos, no models, no network."""
import numpy as np
import pytest

from headshots import group


def blocks(sizes, within=0.85, between=0.15, seed=0):
    """A similarity matrix for `sizes` people: alike inside a group, unlike across."""
    rng = np.random.default_rng(seed)
    n = sum(sizes)
    sim = np.full((n, n), between) + rng.normal(0, 0.01, (n, n))
    at = 0
    for s in sizes:
        sim[at:at + s, at:at + s] = within + rng.normal(0, 0.01, (s, s))
        at += s
    sim = (sim + sim.T) / 2
    np.fill_diagonal(sim, 1.0)
    return sim


def test_finds_the_planted_groups():
    sim = blocks([7, 5, 3, 9])
    got = group.cluster(sim, 0.5)[0]
    assert [len(g) for g in got] == [7, 5, 3, 9]
    assert got[0] == list(range(7))


def test_a_singleton_stays_alone():
    sim = blocks([6, 1, 6])
    got = group.cluster(sim, 0.5)[0]
    assert [len(g) for g in got] == [6, 1, 6]


def test_every_photo_lands_in_exactly_one_group():
    sim = blocks([4, 4, 4, 2, 8])
    got = group.cluster(sim, 0.5)[0]
    flat = sorted(i for g in got for i in g)
    assert flat == list(range(22))


def test_a_loose_cut_merges_and_a_tight_one_splits():
    sim = blocks([5, 5], within=0.8, between=0.4)
    assert len(group.cluster(sim, 0.3)[0]) == 1
    assert len(group.cluster(sim, 0.6)[0]) == 2
    assert len(group.cluster(sim, 0.95)[0]) == 10


def test_average_linkage_resists_one_ambiguous_photo():
    """Single linkage would chain two people through one borderline shot. Average linkage should not."""
    sim = blocks([5, 5], within=0.85, between=0.10)
    sim[4, 5] = sim[5, 4] = 0.72                      # one shot that looks like both
    assert len(group.cluster(sim, 0.5)[0]) == 2


def test_cluster_count_never_falls_as_the_cut_tightens():
    sim = blocks([6, 4, 5])
    counts = [k for _, k in group.sweep(sim)]
    assert counts == sorted(counts)


def test_plateau_picks_the_widest_stable_run():
    counts = [(round(0.30 + i * 0.01, 2), k) for i, k in
              enumerate([2, 3, 4, 4, 5] + [7] * 20 + [9, 11])]
    k, lo, hi, mid = group.plateau(counts)
    assert k == 7
    assert lo == pytest.approx(0.35, abs=1e-6)
    assert lo < mid < hi


def test_empty_input_is_not_a_crash():
    assert group.cluster(np.zeros((0, 0)), 0.5) == ([], [])


@pytest.mark.parametrize("name,expected", [
    ("IMG_3711", 3711), ("IMG_E3711", 3711), ("IMG_O3939", 3939), ("DSC_0042", 42), ("nodigits", 0),
])
def test_shot_number_reads_the_photo_number_not_the_filename(name, expected, tmp_path):
    assert group.shot_number(tmp_path / f"{name}.jpg")[0] == expected


def test_an_edited_photo_sorts_next_to_its_original(tmp_path):
    names = ["IMG_3915.jpg", "IMG_E3721.jpg", "IMG_3720.jpg", "IMG_E3916.jpg"]
    order = [p.name for p in sorted((tmp_path / n for n in names), key=group.shot_number)]
    assert order == ["IMG_3720.jpg", "IMG_E3721.jpg", "IMG_3915.jpg", "IMG_E3916.jpg"]
