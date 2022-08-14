from whad.domain.ble.utils.phy import channel_to_frequency,frequency_to_channel,crc
import pytest

@pytest.mark.parametrize("test_input, expected", [
    ( 2402, 37 ),
    ( 2404, 0 ),
    ( 2406, 1 ),
    ( 2408, 2 ),
    ( 2410, 3 ),
    ( 2412, 4 ),
    ( 2414, 5 ),
    ( 2416, 6 ),
    ( 2418, 7 ),
    ( 2420, 8 ),
    ( 2422, 9 ),
    ( 2424, 10 ),
    ( 2426, 38 ),
    ( 2428, 11 ),
    ( 2430, 12 ),
    ( 2432, 13 ),
    ( 2434, 14 ),
    ( 2436, 15 ),
    ( 2438, 16 ),
    ( 2440, 17 ),
    ( 2442, 18 ),
    ( 2444, 19 ),
    ( 2446, 20 ),
    ( 2448, 21 ),
    ( 2450, 22 ),
    ( 2452, 23 ),
    ( 2454, 24 ),
    ( 2456, 25 ),
    ( 2458, 26 ),
    ( 2460, 27 ),
    ( 2462, 28 ),
    ( 2464, 29 ),
    ( 2466, 30 ),
    ( 2468, 31 ),
    ( 2470, 32 ),
    ( 2472, 33 ),
    ( 2474, 34 ),
    ( 2476, 35 ),
    ( 2478, 36 ),
    ( 2480, 39 ),
    ( "test", None),
    ( 3000, None)
    ])
def test_frequency_to_channel(test_input, expected):
    assert frequency_to_channel(test_input) == expected

@pytest.mark.parametrize("test_input, expected", [
    ( 37, 2402 ),
    ( 0, 2404 ),
    ( 1, 2406 ),
    ( 2, 2408 ),
    ( 3, 2410 ),
    ( 4, 2412 ),
    ( 5, 2414 ),
    ( 6, 2416 ),
    ( 7, 2418 ),
    ( 8, 2420 ),
    ( 9, 2422 ),
    ( 10, 2424 ),
    ( 38, 2426 ),
    ( 11, 2428 ),
    ( 12, 2430 ),
    ( 13, 2432 ),
    ( 14, 2434 ),
    ( 15, 2436 ),
    ( 16, 2438 ),
    ( 17, 2440 ),
    ( 18, 2442 ),
    ( 19, 2444 ),
    ( 20, 2446 ),
    ( 21, 2448 ),
    ( 22, 2450 ),
    ( 23, 2452 ),
    ( 24, 2454 ),
    ( 25, 2456 ),
    ( 26, 2458 ),
    ( 27, 2460 ),
    ( 28, 2462 ),
    ( 29, 2464 ),
    ( 30, 2466 ),
    ( 31, 2468 ),
    ( 32, 2470 ),
    ( 33, 2472 ),
    ( 34, 2474 ),
    ( 35, 2476 ),
    ( 36, 2478 ),
    ( 39, 2480 ),
    ( "test", None ),
    ( 42, None )

    ])
def test_channel_to_frequency(test_input, expected):
    assert channel_to_frequency(test_input) == expected


@pytest.mark.parametrize("test_input, expected", [
    ( "0215110006000461ca0ce41b1e430559ac74e382667051", "545d96" ),
    ])

def test_crc(test_input, expected):
    data = bytes.fromhex(test_input)
    crc_value = bytes.fromhex(expected)
    assert crc(data) == crc_value
