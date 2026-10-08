from ruleflow.core.topologies.nd_space import SpaceState1D


def test_space_state_substitute(space_1d_factory):
    # Using the fixture from conftest.py
    space: SpaceState1D = space_1d_factory([65, 66, 67, 68])  # A, B, C, D
    next_space = space.next_gen()

    # Substitute 'B, C' with 'X, Y, Z'
    delta = next_space.substitute((1, 3), [88, 89, 90])

    assert list(next_space.vec.data) == [65, 88, 89, 90, 68]

    # Validate DeltaCell accurately captured causality
    assert [c.quanta for c in delta.destroyed_cells] == [66, 67]
    assert [c.quanta for c in delta.new_cells] == [88, 89, 90]
    # Verify generations tracked correctly
    assert [c.gen for c in delta.new_cells] == [1, 1, 1]


def test_space_state_overwrite(space_1d_factory):
    space = space_1d_factory([10, 20, 30, 40])
    next_space = space.next_gen()

    # Overwrite starting at index 2, with -1 wildcard skip
    delta = next_space.overwrite(2, [99, -1, 100])

    # Index 2 overwritten by 99, index 3 skipped, index 4 created with 100
    assert list(next_space.vec.data) == [10, 20, 99, 40, 100]

    assert [c.quanta for c in delta.destroyed_cells] == [30]  # 40 wasn't destroyed
    assert [c.quanta for c in delta.new_cells] == [99, 100]


def test_space_state_insert(space_1d_factory):
    space = space_1d_factory([1, 2, 3, 4])
    next_space = space.next_gen()

    delta = next_space.insert(2, (5, 6))

    assert list(next_space.vec.data) == [1, 2, 5, 6, 3, 4]
    assert [c.quanta for c in delta.new_cells] == [5, 6]
    assert len(delta.destroyed_cells) == 0


def test_space_state_delete(space_1d_factory):
    space = space_1d_factory([1, 2, 3, 4])
    next_space = space.next_gen()

    delta = next_space.delete((1, 3))

    assert list(next_space.vec.data) == [1, 4]
    assert [c.quanta for c in delta.destroyed_cells] == [2, 3]
    assert len(delta.new_cells) == 0
