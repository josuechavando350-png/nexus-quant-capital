//! Literal safe-Rust port of NQC019's bounded financial screen.
//! Evidence bits are assertions, NOT authentication. Units are unchanged from NQC019.
pub const MAX_STEPS: usize = 16;
pub const INVALID: u64 = 1;
pub const EVIDENCE_MISSING: u64 = 2;
pub const STATE_MISMATCH: u64 = 4;
pub const TIME_INVALID: u64 = 8;
pub const FUNDING_UNKNOWN: u64 = 16;
pub const PREFIX_INSUFFICIENT: u64 = 32;
pub const OVERFLOW: u64 = 64;
pub const FUNDING_CAP: u64 = 128;
pub const RESIDUAL_FINANCING: u64 = 256;
pub const PROPOSER_UNPAID: u64 = 512;
pub const SPONSOR_MARGIN: u64 = 1024;
pub const OPERATOR_MARGIN: u64 = 2048;
pub const PERSONAL_CAPITAL: u64 = 4096;
pub const PACKAGE_INCOMPLETE: u64 = 8192;
pub const SPONSOR_RESERVE: u64 = 16384;
pub const GENERATION_CHANGED: u64 = 32768;

#[derive(Clone, Copy, Default, Debug)]
pub struct Step {
    pub gas_limit: u64,
    pub max_fee: u64,
    pub gas_used: u64,
    pub effective_price: u64,
    pub funding_before: u128,
    pub value_to_sponsor: u128,
    pub native_credit_after: u128,
}
#[derive(Clone, Debug, Default)]
pub struct Candidate {
    pub chain_id: u64,
    pub epoch: u64,
    pub current_epoch: u64,
    pub block_number: u64,
    pub state_numbers: [u64; 4],
    pub state_index: u64,
    pub state_indices: [u64; 4],
    pub state_hashes: [[u8; 32]; 4],
    pub now_ns: u64,
    pub received_ns: u64,
    pub max_age_ns: u64,
    pub cutoff_ns: u64,
    pub quote_expiry_ns: u64,
    pub send_budget_ns: u64,
    pub evidence_mask: u64,
    pub funding_known: u64,
    pub package_complete: u64,
    pub n: u64,
    pub operator_initial: u128,
    pub funding_cap: u128,
    pub sponsor_reserve: u128,
    pub overhead_reserve: u128,
    pub overhead_cost: u128,
    pub sponsor_other_inflows: u128,
    pub proposer_required: u128,
    pub proposer_paid: u128,
    pub other_costs: u128,
    pub min_sponsor_margin: u128,
    pub operator_weth_new: u128,
    pub min_operator_weth: u128,
    pub steps: [Step; MAX_STEPS],
}
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Screen {
    pub reasons: u64,
    pub total_funding: u128,
    pub total_operator_gas: u128,
    pub refunded: u128,
    pub residual: u128,
    pub sponsor_margin: u128,
}

#[inline(always)]
pub fn screen(c: &Candidate) -> Screen {
    screen_at(c, c.now_ns)
}
/// Read the same immutable candidate with a fresh clock value, avoiding a whole-object copy.
#[inline(never)]
pub fn screen_at(c: &Candidate, now_ns: u64) -> Screen {
    let mut r = Screen::default();
    if c.n == 0
        || c.n > 16
        || c.funding_known > 1
        || c.package_complete > 1
        || c.evidence_mask > 63
        || c.overhead_cost > c.overhead_reserve
    {
        r.reasons = INVALID;
        return r;
    }
    if c.evidence_mask != 63 {
        r.reasons |= EVIDENCE_MISSING;
    }
    if c.funding_known == 0 {
        r.reasons |= FUNDING_UNKNOWN;
    }
    if c.package_complete == 0 {
        r.reasons |= PACKAGE_INCOMPLETE;
    }
    if c.operator_initial != 0 {
        r.reasons |= PERSONAL_CAPITAL;
    }
    if c.epoch == 0 || c.epoch != c.current_epoch {
        r.reasons |= GENERATION_CHANGED;
    }
    if c.chain_id != 1 || c.block_number == 0 || c.state_hashes[0] == [0; 32] {
        r.reasons |= STATE_MISMATCH;
    }
    for k in 0..4 {
        if c.state_numbers[k] != c.block_number
            || c.state_indices[k] != c.state_index
            || c.state_hashes[k] != c.state_hashes[0]
        {
            r.reasons |= STATE_MISMATCH;
        }
    }
    if c.received_ns == 0
        || c.max_age_ns == 0
        || c.cutoff_ns == 0
        || c.quote_expiry_ns == 0
        || now_ns < c.received_ns
        || now_ns - c.received_ns > c.max_age_ns
        || c.send_budget_ns == 0
        || now_ns >= c.cutoff_ns
        || now_ns >= c.quote_expiry_ns
        || c.send_budget_ns >= c.cutoff_ns - now_ns
        || c.send_budget_ns >= c.quote_expiry_ns - now_ns
    {
        r.reasons |= TIME_INVALID;
    }
    macro_rules! add {
        ($a:expr, $b:expr) => {
            match ($a).checked_add($b) {
                Some(v) => v,
                None => {
                    r.reasons |= OVERFLOW;
                    return r;
                }
            }
        };
    }
    let mut balance = c.operator_initial;
    for s in &c.steps[..c.n as usize] {
        if s.gas_limit == 0 || s.gas_used > s.gas_limit || s.effective_price > s.max_fee {
            r.reasons |= INVALID;
            return r;
        }
        let reserve = u128::from(s.gas_limit) * u128::from(s.max_fee);
        let cost = u128::from(s.gas_used) * u128::from(s.effective_price);
        let needed = add!(reserve, s.value_to_sponsor);
        balance = add!(balance, s.funding_before);
        r.total_funding = add!(r.total_funding, s.funding_before);
        if balance < needed {
            r.reasons |= PREFIX_INSUFFICIENT;
            return r;
        }
        balance -= cost;
        balance -= s.value_to_sponsor;
        balance = add!(balance, s.native_credit_after);
        r.total_operator_gas = add!(r.total_operator_gas, cost);
        r.refunded = add!(r.refunded, s.value_to_sponsor);
    }
    r.residual = balance;
    if r.total_funding > c.funding_cap {
        r.reasons |= FUNDING_CAP;
    }
    if balance != 0 {
        r.reasons |= RESIDUAL_FINANCING;
    }
    let initial_required = add!(r.total_funding, c.overhead_reserve);
    let initial_required = add!(initial_required, c.proposer_paid);
    let income = add!(c.sponsor_other_inflows, r.refunded);
    let expense = add!(r.total_funding, c.overhead_cost);
    let expense = add!(expense, c.proposer_paid);
    let expense = add!(expense, c.other_costs);
    if initial_required > c.sponsor_reserve {
        r.reasons |= SPONSOR_RESERVE;
    }
    if c.proposer_paid < c.proposer_required {
        r.reasons |= PROPOSER_UNPAID;
    }
    if income <= expense {
        r.reasons |= SPONSOR_MARGIN;
    } else {
        r.sponsor_margin = income - expense;
        if r.sponsor_margin < c.min_sponsor_margin {
            r.reasons |= SPONSOR_MARGIN;
        }
    }
    if c.operator_weth_new == 0 || c.operator_weth_new < c.min_operator_weth {
        r.reasons |= OPERATOR_MARGIN;
    }
    r
}

/// Strict NQC019 text format, retained for differential tests and matched corpora.
pub fn parse(line: &str) -> Result<Candidate, String> {
    let mut fields = line.split_whitespace();
    fn num(it: &mut std::str::SplitWhitespace<'_>) -> Result<u128, String> {
        let s = it.next().ok_or("missing field")?;
        if s.is_empty() || s.len() > 39 || !s.bytes().all(|b| b.is_ascii_digit()) {
            return Err("invalid integer".into());
        }
        s.parse().map_err(|_| "integer overflow".into())
    }
    macro_rules! word {
        () => {
            u64::try_from(num(&mut fields)?).map_err(|_| "u64 overflow")?
        };
    }
    let mut c = Candidate {
        chain_id: word!(),
        epoch: word!(),
        current_epoch: word!(),
        block_number: word!(),
        ..Candidate::default()
    };
    for x in &mut c.state_numbers {
        *x = word!();
    }
    c.state_index = word!();
    for x in &mut c.state_indices {
        *x = word!();
    }
    for h in &mut c.state_hashes {
        let s = fields.next().ok_or("missing hash")?;
        if s.len() != 64
            || !s
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            return Err("invalid hash".into());
        }
        for (i, x) in h.iter_mut().enumerate() {
            *x = u8::from_str_radix(&s[i * 2..i * 2 + 2], 16).map_err(|_| "hash")?;
        }
    }
    c.now_ns = word!();
    c.received_ns = word!();
    c.max_age_ns = word!();
    c.cutoff_ns = word!();
    c.quote_expiry_ns = word!();
    c.send_budget_ns = word!();
    c.evidence_mask = word!();
    c.funding_known = word!();
    c.package_complete = word!();
    c.n = word!();
    if c.n > 16 {
        return Err("too many steps".into());
    }
    c.operator_initial = num(&mut fields)?;
    c.funding_cap = num(&mut fields)?;
    c.sponsor_reserve = num(&mut fields)?;
    c.overhead_reserve = num(&mut fields)?;
    c.overhead_cost = num(&mut fields)?;
    c.sponsor_other_inflows = num(&mut fields)?;
    c.proposer_required = num(&mut fields)?;
    c.proposer_paid = num(&mut fields)?;
    c.other_costs = num(&mut fields)?;
    c.min_sponsor_margin = num(&mut fields)?;
    c.operator_weth_new = num(&mut fields)?;
    c.min_operator_weth = num(&mut fields)?;
    for s in &mut c.steps[..c.n as usize] {
        s.gas_limit = word!();
        s.max_fee = word!();
        s.gas_used = word!();
        s.effective_price = word!();
        s.funding_before = num(&mut fields)?;
        s.value_to_sponsor = num(&mut fields)?;
        s.native_credit_after = num(&mut fields)?;
    }
    if fields.next().is_some() {
        return Err("extra field".into());
    }
    Ok(c)
}
impl Screen {
    pub fn line(self) -> String {
        format!(
            "{} {} {} {} {} {}",
            self.reasons,
            self.total_funding,
            self.total_operator_gas,
            self.refunded,
            self.residual,
            self.sponsor_margin
        )
    }
}
