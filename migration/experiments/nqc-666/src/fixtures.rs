//! SYNTHETIC laboratory scenarios only. Never market data or provider commitments.
use crate::{
    engine::{Anchor, Integrity, Key, Update},
    financial::{Candidate, Step},
    third_eye::{Basis, Position, Scenario},
};
pub fn financial(n: usize, seed: u64) -> Candidate {
    assert!((1..=16).contains(&n));
    let mut c = Candidate {
        chain_id: 1,
        epoch: 1,
        current_epoch: 1,
        block_number: 500,
        state_numbers: [500; 4],
        state_index: 1,
        state_indices: [1; 4],
        state_hashes: [[0xab; 32]; 4],
        now_ns: 200000,
        received_ns: 100000,
        max_age_ns: 1000000,
        cutoff_ns: 10000000,
        quote_expiry_ns: 10000000,
        send_budget_ns: 500000,
        evidence_mask: 63,
        funding_known: 1,
        package_complete: 1,
        n: n as u64,
        funding_cap: 300000000000000000,
        sponsor_reserve: 1000000000000000000,
        overhead_reserve: 200000000000000,
        overhead_cost: 84000000000000,
        sponsor_other_inflows: 100000000000000000,
        proposer_required: 40000000000000000,
        proposer_paid: 40000000000000000,
        other_costs: 1000000000000,
        min_sponsor_margin: 1,
        operator_weth_new: 159365645570551238,
        min_operator_weth: 1,
        ..Candidate::default()
    };
    for (k, s) in c.steps[..n].iter_mut().enumerate() {
        let gas = 21000 + (seed.wrapping_mul(7919).wrapping_add(k as u64 * 31) % 200000);
        *s = Step {
            gas_limit: gas,
            max_fee: 3000000000,
            gas_used: gas - 1000,
            effective_price: 2000000000,
            ..Step::default()
        };
    }
    c.steps[n - 1].max_fee = c.steps[n - 1].effective_price;
    c.steps[n - 1].gas_used = c.steps[n - 1].gas_limit;
    let cost: u128 = c.steps[..n]
        .iter()
        .map(|s| u128::from(s.gas_used) * u128::from(s.effective_price))
        .sum();
    c.steps[0].funding_before = c.funding_cap;
    c.steps[n - 1].value_to_sponsor = c.funding_cap - cost;
    c
}
pub fn update(c: Candidate, slot: usize) -> Update {
    let mut borrower = [0x11; 20];
    borrower[..8].copy_from_slice(&(slot as u64).to_le_bytes());
    let key = Key {
        market: [0x22; 32],
        borrower,
    };
    let mut nonces = [0; 16];
    let mut dependencies = [0; 16];
    for k in 0..16 {
        nonces[k] = 100 + k as u64;
        dependencies[k] = ((1u32 << k) - 1) as u16;
    }
    let integrity = Integrity {
        key,
        anchor: Anchor {
            chain: 1,
            block: c.block_number,
            hash: c.state_hashes[0],
        },
        plan_hash: [0x33; 32],
        code_hash: [0x44; 32],
        required_code_hash: [0x44; 32],
        oracle_at: 100000,
        oracle_max_age: 1000000,
        route_through: 1000000,
        nonce_start: 100,
        nonces,
        dependencies,
        success_mask: ((1u32 << c.n) - 1) as u16,
        required_builder_payment: 1,
        builder_paid: 1,
        slippage_bps: 50,
        max_slippage_bps: 100,
        quoted_net_lower: Some(c.operator_weth_new),
        financing_confirmed: Some(true),
        non_recourse: Some(true),
    };
    Update {
        financial: c,
        integrity,
        position: Position {
            basis: Basis::SyntheticFixture,
            debt: Some(10001 + slot as u128),
            max_borrow: Some(10000),
            near_bps: 100,
        },
        scenario: Some(Scenario {
            interest_low: 1,
            interest_high: 50,
            future_max_borrow_low: 9800,
            future_max_borrow_high: 10200,
            through_ns: 1000000,
        }),
        inclusion_ppm: Some(500000),
        failure_loss: Some(0),
    }
}
