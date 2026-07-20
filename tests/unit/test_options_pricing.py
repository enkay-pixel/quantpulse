import math

import pytest

from quantpulse.options.pricing import black_scholes, years_to_expiry

# Reference case: spot=100, strike=100, 1y, r=5%, iv=20%
SPOT, STRIKE, T, R, IV = 100.0, 100.0, 1.0, 0.05, 0.20


def test_atm_call_price_matches_known_value() -> None:
    call = black_scholes(SPOT, STRIKE, T, R, IV, "call")
    # Standard textbook value for these inputs is ~10.45.
    assert call.price == pytest.approx(10.45, abs=0.05)


def test_put_call_parity() -> None:
    call = black_scholes(SPOT, STRIKE, T, R, IV, "call")
    put = black_scholes(SPOT, STRIKE, T, R, IV, "put")
    # C - P == S - K*e^{-rT}
    lhs = call.price - put.price
    rhs = SPOT - STRIKE * math.exp(-R * T)
    assert lhs == pytest.approx(rhs, abs=1e-6)


def test_atm_call_delta_near_half() -> None:
    call = black_scholes(SPOT, STRIKE, T, R, IV, "call")
    assert 0.5 < call.delta < 0.65  # slightly above 0.5 due to drift


def test_call_and_put_delta_differ_by_one() -> None:
    call = black_scholes(SPOT, STRIKE, T, R, IV, "call")
    put = black_scholes(SPOT, STRIKE, T, R, IV, "put")
    assert call.delta - put.delta == pytest.approx(1.0, abs=1e-9)


def test_gamma_and_vega_shared_and_positive() -> None:
    call = black_scholes(SPOT, STRIKE, T, R, IV, "call")
    put = black_scholes(SPOT, STRIKE, T, R, IV, "put")
    assert call.gamma == pytest.approx(put.gamma, abs=1e-9)  # gamma identical call/put
    assert call.vega == pytest.approx(put.vega, abs=1e-9)
    assert call.gamma > 0
    assert call.vega > 0


def test_theta_negative_for_long_options() -> None:
    assert black_scholes(SPOT, STRIKE, T, R, IV, "call").theta < 0
    assert black_scholes(SPOT, STRIKE, T, R, IV, "put").theta < 0


def test_deep_itm_call_delta_near_one() -> None:
    call = black_scholes(200.0, 100.0, T, R, IV, "call")
    assert call.delta > 0.98


def test_deep_otm_call_near_worthless() -> None:
    call = black_scholes(50.0, 100.0, T, R, IV, "call")
    assert call.price < 0.5
    assert call.delta < 0.02


def test_degenerate_inputs_fall_back_to_intrinsic() -> None:
    expired = black_scholes(120.0, 100.0, 0.0, R, IV, "call")
    assert expired.price == pytest.approx(20.0)
    assert expired.gamma == 0.0
    zero_vol_put = black_scholes(80.0, 100.0, T, R, 0.0, "put")
    assert zero_vol_put.price == pytest.approx(20.0)


def test_years_to_expiry() -> None:
    assert years_to_expiry(365) == pytest.approx(1.0)
    assert years_to_expiry(0) == 0.0
    assert years_to_expiry(-5) == 0.0
