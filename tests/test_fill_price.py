from bot import _extract_execution_price


def test_extract_execution_price_uses_actual_fill_price():
    response = {
        "order": {"price": "0.78"},
        "fills": [{"price": "0.69", "size": "1"}],
    }

    assert _extract_execution_price(response, 0.78) == 0.69


def test_extract_execution_price_falls_back_to_quote():
    assert _extract_execution_price({"status": "accepted"}, 0.78) == 0.78
