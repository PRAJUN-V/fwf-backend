from app.games import snakes_and_ladders as snl


def test_roll_die_in_range():
    for _ in range(200):
        value = snl.roll_die()
        assert 1 <= value <= 6


def test_normal_move():
    new_pos, jumped = snl.resolve_move(2, 3)
    assert new_pos == 5
    assert jumped is None


def test_ladder_move():
    # 1 -> 38 is a ladder; landing on 1 from 0 with a roll of 1.
    new_pos, jumped = snl.resolve_move(0, 1)
    assert new_pos == 38
    assert jumped == 1


def test_snake_move():
    # 16 -> 6 is a snake; reach 16 from 10 with a roll of 6.
    new_pos, jumped = snl.resolve_move(10, 6)
    assert new_pos == 6
    assert jumped == 16


def test_overshoot_stays_in_place():
    new_pos, jumped = snl.resolve_move(98, 5)
    assert new_pos == 98
    assert jumped is None


def test_exact_landing_wins():
    new_pos, _ = snl.resolve_move(97, 3)
    assert new_pos == 100
    assert snl.is_winning_position(new_pos)


def test_snakes_and_ladders_disjoint():
    assert set(snl.LADDERS).isdisjoint(set(snl.SNAKES))
