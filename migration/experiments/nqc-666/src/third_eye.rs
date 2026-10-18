//! Conditional predictions over supplied, exact-boundary loan-asset amounts.
//! The Morpho U256/IRM/oracle adapter is deliberately outside this experiment.
//! No prediction is promoted into an observed eligibility or an authorization.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Observed {
    Unknown,
    Healthy,
    Near,
    Eligible,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Prediction {
    Unknown,
    RemainsHealthy,
    MayCross,
    CrossesUnderAssumptions,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Basis {
    Unknown,
    SyntheticFixture,
}
#[derive(Clone, Copy, Debug)]
pub struct Position {
    /// There is intentionally no authenticated-market variant until an adapter exists.
    pub basis: Basis,
    /// Already rounded up by the upstream Morpho adapter, in atomic loan units.
    pub debt: Option<u128>,
    /// Already rounded down using collateral, oracle and LLTV, in the SAME units.
    pub max_borrow: Option<u128>,
    pub near_bps: u16,
}
#[derive(Clone, Copy, Debug)]
pub struct Scenario {
    /// Interest increments supplied by a bounded IRM scenario, NOT observed interest.
    pub interest_low: u128,
    pub interest_high: u128,
    pub future_max_borrow_low: u128,
    pub future_max_borrow_high: u128,
    pub through_ns: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Assessment {
    pub basis: Basis,
    pub observed: Observed,
    pub prediction: Prediction,
}
pub fn assess(p: Position, scenario: Option<Scenario>, now: u64) -> Assessment {
    let unknown = Assessment {
        basis: p.basis,
        observed: Observed::Unknown,
        prediction: Prediction::Unknown,
    };
    if p.basis == Basis::Unknown {
        return unknown;
    }
    let (Some(debt), Some(cap)) = (p.debt, p.max_borrow) else {
        return unknown;
    };
    if p.near_bps > 10000 {
        return unknown;
    }
    // Morpho: equality is healthy; zero debt cannot be liquidatable.
    let observed = if debt > cap {
        Observed::Eligible
    } else if debt == 0 {
        Observed::Healthy
    } else {
        let Some(lhs) = (cap - debt).checked_mul(10000) else {
            return unknown;
        };
        let Some(rhs) = cap.checked_mul(u128::from(p.near_bps)) else {
            return unknown;
        };
        if lhs <= rhs {
            Observed::Near
        } else {
            Observed::Healthy
        }
    };
    let prediction = (|| {
        let s = scenario?;
        if s.through_ns < now
            || s.interest_low > s.interest_high
            || s.future_max_borrow_low > s.future_max_borrow_high
        {
            return None;
        }
        let low = debt.checked_add(s.interest_low)?;
        let high = debt.checked_add(s.interest_high)?;
        Some(if low > s.future_max_borrow_high {
            Prediction::CrossesUnderAssumptions
        } else if high > s.future_max_borrow_low {
            Prediction::MayCross
        } else {
            Prediction::RemainsHealthy
        })
    })()
    .unwrap_or(Prediction::Unknown);
    Assessment {
        basis: p.basis,
        observed,
        prediction,
    }
}

/// Expected value is an inference from supplied probability and loss bounds.
/// There is no default probability; missing inputs exclude the candidate from ranking.
pub fn expected_net(
    net_lower: u128,
    inclusion_ppm: Option<u32>,
    failure_loss: Option<u128>,
) -> Option<u128> {
    let p = u128::from(inclusion_ppm?);
    if p > 1_000_000 {
        return None;
    }
    let gain = net_lower.checked_mul(p)? / 1_000_000;
    let loss = failure_loss?.checked_mul(1_000_000 - p)?;
    let loss = loss / 1_000_000 + u128::from(loss % 1_000_000 != 0);
    gain.checked_sub(loss).filter(|v| *v > 0)
}
