from app.services.schedule_utils import slot_indexes_for_label


def test_slot_indexes_for_standard_block():
    assert slot_indexes_for_label("13:00 - 14:00") == [3]


def test_slot_indexes_for_composed_block():
    assert slot_indexes_for_label("13:00 - 15:00") == [3, 4]


def test_slot_indexes_for_standard_afternoon_block():
    assert slot_indexes_for_label("14:00 - 16:00") == [4]

